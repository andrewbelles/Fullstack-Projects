#include <cassert>
#include <iostream> 
#include <algorithm>
#include <vector> 
#include <unordered_map>
#include <unordered_set>
#include <cmath>
#include <string>
#include <fstream> 
#include <array>
#include <sqlite3.h>
#include <limits>
#include <queue> 
#include <cstdint>

// Custom hash for std::pair<int, std::string>
struct IntStringHash {
  size_t operator()(const std::pair<int, std::string>& pair) const {
    return std::hash<long long>()(((long long)pair.first << 32) 
        ^ std::hash<std::string>()(pair.second));
  }
};

struct IntIntHash {
  size_t operator()(const std::pair<int, int>& pair) const {
    return std::hash<uint64_t>()(uint64_t(pair.first) << 32 ^ uint32_t(pair.second));
  }
};

struct Assignment {
  int slot; 
  std::string location; 
  int user_id;

  Assignment(int slot_num, std::string location, int user_id)
    : slot(slot_num), location(std::move(location)), user_id(user_id) {}
};

// Single edge in residual graph for max-flow 
struct Edge {
  int to;         // dest  
  int reverse;    // index to u from v's "perspective" 
  int capacity;   // Capacity (Remaining unused free-shifts) 
  int cost; 
};

// Global constants / constexprs
constexpr int FIRST_SLOT  = 44; 
constexpr int LAST_SLOT   = 2; 
constexpr int TOTAL_SLOTS = 48; 
constexpr int COST_SCALE  = 1000;
constexpr double tol      = 1e-3;
const std::array<std::string, 5> GENERAL = {"Front1","Front2","Side","Back","Runner"};
const std::array<std::string, 2> BAR = {"Bar1", "Bar2"};

// Wrapper to output given sqlite error to log 
void 
sqlerr(sqlite3* db, const char* msg) {
  // TODO: Get date/time for error log file name 
  std::ofstream err("logs/error.log");  
  err << msg << " : " << sqlite3_errmsg(db) << '\n';
  if (db) 
    sqlite3_close(db);

  std::exit(1);
}

void 
fetch_users(sqlite3* db, 
            std::vector<int>& users, 
            std::unordered_map<int, int>& counts,
            std::unordered_map<int, std::string>& status_map) 
{
  const char* sql_users = "SELECT id, status FROM users;";  
  sqlite3_stmt* stmt = nullptr;  
  // Prepare users query
  if (sqlite3_prepare_v2(db, sql_users, -1, &stmt, nullptr) != SQLITE_OK)
    sqlerr(db, "Failed to prepare users query");

  // Pull users from query
  while (sqlite3_step(stmt) == SQLITE_ROW) {
    int uid = sqlite3_column_int(stmt, 0);
    const char* status = reinterpret_cast<const char*>(
      sqlite3_column_text(stmt, 1)
    );
    users.push_back(uid);
    counts[uid] = 0;
    // Fall back to GENERAL if empty (shouldn't happen)
    status_map[uid] = status ? status : "GENERAL";
  }
  sqlite3_finalize(stmt);

  const char* sql_counts = "SELECT user_id, COUNT(*)"
                           "FROM shifts "
                           "GROUP BY user_id;";
  // Prepare counts query 
  if (sqlite3_prepare_v2(db, sql_counts, -1, &stmt, nullptr) != SQLITE_OK)
    sqlerr(db, "Failed to prepare counts query");

  // Pull counts from query 
  while(sqlite3_step(stmt) == SQLITE_ROW) {
    int uid   = sqlite3_column_int(stmt, 0);
    int count = sqlite3_column_int(stmt, 1);
    counts[uid] = count;
  }
  sqlite3_finalize(stmt);
}

void 
fetch_filled_shifts(sqlite3* db, 
                    const std::string& week, 
                    std::vector<Assignment>& filled) 
{
  const char* fill_query = "SELECT slot, location, user_id "
                           "FROM shifts "
                           "WHERE week = ?;";
  sqlite3_stmt* stmt = nullptr; 

  if (sqlite3_prepare_v2(db, fill_query, -1, &stmt, nullptr) != SQLITE_OK)
    sqlerr(db, "Failed to prepare filled shifts query");

  if (sqlite3_bind_text(stmt, 1, week.c_str(), -1, SQLITE_STATIC) != SQLITE_OK) 
    sqlerr(db, "Failed to bind week parameter");

  while(sqlite3_step(stmt) == SQLITE_ROW) {
    int slot = sqlite3_column_int(stmt, 0);
    const char* location = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 1));
    int uid  = sqlite3_column_int(stmt, 2);
    filled.emplace_back(slot, std::string(location), uid);
  }
  sqlite3_finalize(stmt);
}

void 
delete_old_shifts(sqlite3* db, 
                  const std::string& week)
{
  const char* del_query = "DELETE FROM shifts WHERE week = ?;";
  sqlite3_stmt* stmt = nullptr; 

  if (sqlite3_prepare_v2(db, del_query, -1, &stmt, nullptr) != SQLITE_OK) {
    sqlerr(db, "Failed to prepare delete statement");
  }

  sqlite3_bind_text(stmt, 1, week.c_str(), -1, SQLITE_STATIC); 
  if (sqlite3_step(stmt) != SQLITE_DONE) {
    sqlerr(db, "Failed to delete old shifts");
  }
  sqlite3_finalize(stmt);
}

void 
insert_manifest(sqlite3* db,
                const std::string& week,
                const std::vector<Assignment>& final_manifest)
{
  const char* ins_query = "INSERT INTO shifts (user_id, week, slot, location) "
                          "VALUES (?, ?, ?, ?);";
  sqlite3_stmt* stmt = nullptr;

  if (sqlite3_prepare_v2(db, ins_query, -1, &stmt, nullptr) != SQLITE_OK) {
    sqlerr(db, "Failed to prepare insert statement");
  }

  for (auto& assignment : final_manifest) {
    sqlite3_bind_int(stmt, 1, assignment.user_id);
    sqlite3_bind_text(stmt, 2, week.c_str(), -1, SQLITE_STATIC);
    sqlite3_bind_int(stmt, 3, assignment.slot);
    sqlite3_bind_text(stmt, 4, assignment.location.c_str(), -1, SQLITE_STATIC);

    if (sqlite3_step(stmt) != SQLITE_DONE) {
      sqlerr(db, "Failed to insert shifts");
    }
    sqlite3_reset(stmt);
  }
  sqlite3_finalize(stmt);
}

// Adds forward edge with given capacity and reverse edge with 0 capacity  
// u and v are vertices 
inline void
add_edge(std::vector<std::vector<Edge>>& graph, 
         int u, 
         int v, 
         int capacity,
         int cost=0) {
  // forward edge 
  graph[u].push_back({v, static_cast<int>(graph[v].size()), capacity, cost});
  // 0 capacity, reverse edge
  graph[v].push_back({u, static_cast<int>(graph[u].size()) - 1, 0, cost});
}

// Build manifest based on logistic probability curve. 
// Over time, higher shift count advantage lessens 
void 
build_manifest(std::vector<std::vector<Edge>>& graph,
               const std::vector<int>& slots,
               const std::vector<int>& eligible, 
               const std::vector<std::pair<int, std::string>>& missing,
               const std::unordered_map<int, int>& capacity_map,
               const std::unordered_set<std::pair<int, int>, IntIntHash>& uid_has_slot,
               const std::unordered_map<int, double>& weights,
               double smoothing_factor)
{
  // Get const sizes  
  const int eligible_count = eligible.size();
  const int missing_count  = missing.size();
  const int slots_count    = slots.size();
  const int N = eligible_count + missing_count + 2;
  int source = 0;
  int first_user = 1; 
  int user_start = 1 + eligible_count;
  int slot_start = user_start + eligible_count * slots_count;
  int sink = slot_start + missing_count;

  graph.assign(sink + 1, {});

  // Initialize graph 
  for (int i = 0; i < eligible_count; i++) {
    int uid = eligible[i];
    add_edge(graph, source, first_user + i, capacity_map.at(uid), 0);
  }

  for (int i = 0; i < eligible_count; i++) {
    int node = first_user + i;
    for (int k = 0; k < slots_count; k++) {
      int jnode = user_start + i * slots_count + k;
      add_edge(graph, node, jnode, 1, 0);
    }
  }

  for (int i = 0; i < eligible_count; i++) {
    int uid  = eligible[i];
    
    for (int j = 0; j < slots_count; j++) {
      int slot_idx = slots[j];
      int user_at_slot = user_start + i * slots_count + j;

      for (int k = 0; k < missing_count; k++) {
        if (missing[k].first != slot_idx)
          continue; 

        if (uid_has_slot.count({uid, slot_idx}))
          continue;
        
        int cost = int(std::round(smoothing_factor * weights.at(uid)));
        add_edge(graph, user_at_slot, slot_start + k, 1, cost);
      }
    }
  }

  for (int j = 0; j < missing_count; j++) 
    add_edge(graph, slot_start + j, sink, 1, 0);
}

// Finds the minimum-cost maximum flow from "source" to "sink" in a directed graph.
// Returns a pair {totalFlow, totalCost}
std::pair<int, int>
get_flow_and_cost(int source,
                  int sink,
                  std::vector<std::vector<Edge>>& graph)
{
  const int N = graph.size();
  constexpr int limit = std::numeric_limits<int>::max() / 2;
  int flow = 0, flow_cost = 0; 
  std::vector<int> potential(N, 0);

  // Repeatedly augment along shortest path in a reduced cost graph
  while (true) {
    // Initialize vars to run dijkstra
    std::vector<int> distance(N, limit);
    std::vector<int> prev_node(N, -1), prev_edge(N, -1);
    distance[source] = 0;

    // Type alias other this looks fucking disgusting 
    using IntPair = std::pair<int, int>; 
    std::priority_queue<IntPair, std::vector<IntPair>, std::greater<IntPair>> distance_queue;
    distance_queue.emplace(0, source);

    // Djikstra loop. finds shortest path of reduced costs 
    //
    while (!distance_queue.empty()) {
      auto [current_distance, u] = distance_queue.top();
      distance_queue.pop();

      if (current_distance > distance[u])
        continue;

      for (int i = 0; i < int(graph[u].size()); i++) {
        const Edge& edge = graph[u][i];
        // No flow to send 
        if (edge.capacity <= 0)
          continue; 

        // get reduced cost 
        int v = edge.to;
        int cost_through_edge = current_distance + edge.cost 
          + potential[u] - potential[v];

        if (cost_through_edge < distance[v]) {
          distance[v] = cost_through_edge;
          prev_node[v] = u;
          prev_edge[v] = i;
          distance_queue.emplace(cost_through_edge, v);
        }
      }
    }

    // indicates sink is unreachable 
    if (distance[sink] == limit)
      break;

    // Update potentials to keep > 0 
    for (int v = 0; v < N; v++) {
      if (distance[v] < limit)
        potential[v] += distance[v];
    }

    // Find bottleneck capacity on path
    int push_flow = limit * 2;
    for (int v = sink; v != source; v = prev_node[v]) {
      const Edge& edge = graph[prev_node[v]][prev_edge[v]];
      push_flow = std::min(push_flow, edge.capacity);
    }

    // Apply flow and accumulate cost of path
    for (int v = sink; v != source; v = prev_node[v]) {
      Edge& edge = graph[prev_node[v]][prev_edge[v]];
      Edge& reverse_edge = graph[v][edge.reverse]; 

      edge.capacity -= push_flow;
      reverse_edge.capacity += push_flow;
      flow_cost += push_flow * edge.cost;
    }
    flow += push_flow;
  }

  return {flow, flow_cost};
}

std::vector<Assignment>
extract_matching(const std::vector<std::vector<Edge>>& graph,
                 const std::vector<int>& eligible,
                 const std::vector<std::pair<int, std::string>>& missing,
                 int slots_count,
                 int user_start, 
                 int slot_start)
{
  const int eligible_count(eligible.size());
  const int missing_count(missing.size());
  std::vector<Assignment> result;

  for (int i = 0; i < eligible_count; i++) {
    int uid = eligible[i];
    for (int j = 0; j < slots_count; j++) {
      int node = user_start + i * slots_count + j;
      for (const auto& edge : graph[node]) {
        
        if (edge.to >= slot_start 
            && edge.to < slot_start + missing_count
            && edge.capacity == 0)
        {
          auto [slot, location] = missing[edge.to - slot_start];
          result.emplace_back(slot, location, uid);
        }
      }
    }
  }
  return result;
}

// Checks if graph is under fitness threshold of fairness 
// Gini based fitness 
bool 
is_fair(const std::vector<Assignment>& manifest,
        const std::unordered_map<int, int>& counts)
{
  std::unordered_map<int, int> final_counts = counts; 
  for (auto &assignment : manifest) {
    final_counts[assignment.user_id]++;
  }

  int N = final_counts.size();
  if (N == 0) 
    return true; 

  double threshold = 0.20 + 0.30 / N;
  threshold = (threshold > 1.0) ? 1.0 : threshold;

  double sum = 0.0; 
  for (auto& [_, capacity] : final_counts)
    sum += capacity; 

  double mean = sum / N; 
  if (mean < tol)
    return true; 

  double difference = 0.0; 
  for (auto& [_, capacity_i] : final_counts) {
    for (auto& [_, capacity_j] : final_counts) {
      difference += std::abs(capacity_i - capacity_j);
    }
  }

  double gini = difference / (2.0 * N*N * mean);
  return gini <= threshold;
}

std::vector<Assignment>
compute_flow(const std::vector<int>& slots,
             const std::vector<int>& eligible,
             const std::vector<std::pair<int, std::string>>& missing,
             const std::unordered_map<int, int>& counts,
             std::unordered_map<int, int>& capacity_map,
             std::unordered_set<std::pair<int, int>, IntIntHash>& uid_has_slot,
             const std::unordered_map<int, double>& weights,
             double smoothing_factor,
             bool verbose=false)
{
  // Setup local parameters 
  const int slots_count    = int(slots.size());
  const int eligible_count = int(eligible.size());
  const int missing_count  = int(missing.size());

  int source     = 0;
  int first_user = 1;
  int user_start = first_user + eligible_count;      
  int slot_start = user_start + eligible_count * slots_count;
  int sink       = slot_start + missing_count;
  const int N          = sink + 1;
  std::vector<std::vector<Edge>> graph(N);


  // Data structure to hold the final manifest of slot, location, uid tuples
  std::vector<Assignment> manifest; 
  for (double smooth_factor = 0.0; smooth_factor <= 1.0 + tol; smooth_factor += 0.1) {
    if (verbose)
      std::cout << "Smoothing Factor: " << smooth_factor << '\n';

    build_manifest(
      graph,
      slots,
      eligible,
      missing,
      capacity_map,
      uid_has_slot,
      weights,
      smooth_factor
    );
    
    if (verbose)
      std::cout << "Got manifest\n";

    // Expecting std::pair<int, int> 
    auto [flow, cost] = get_flow_and_cost(source, sink, graph);  
    if (verbose)
      std::cout << "Flow and Cost: " << "(" << flow << "," << cost << ")\n";

    if (flow < missing_count) {
      if (verbose)
        std::cout << "Incomplete Flow\n";
      continue;
    }

    // Get matching from cost 
    std::vector<Assignment> matching = extract_matching(
      graph,
      eligible,
      missing,
      slots.size(),
      user_start,
      slot_start
    ); 

    // TODO: This is sloppy!
    manifest = std::move(matching);
    break;

    // Check if fair enough and break early if so 
    //if (is_fair(matching, counts)) {
    //  manifest = std::move(matching);
    //  break;
    //}
  }

  return manifest; 
}

// Usage: ./fill_shifts <sql_path> <week> //opt <-v (verbos)>
int 
main(int argc, char* argv[]) {
  if (argc < 3) {
    std::ofstream err("logs/error.log");
    err << "Invalid usage\n";
    return 1; 
  }

  const std::string sql_path = argv[1];
  const std::string week     = argv[2]; 
  bool verbose = false;

  // Guard out of bounds. Leave verbose empty if omitted 
  if (argc == 4) {
    verbose = true; 
  }

  sqlite3* db = nullptr; 
  if (sqlite3_open(sql_path.c_str(), &db) != SQLITE_OK) 
    sqlerr(db, "Failed opening database");

  std::vector<int> users; 
  std::unordered_map<int, int> counts; 
  std::unordered_map<int, std::string> status_map;

  fetch_users(db, users, counts, status_map); 
  
  // debug print 
  if (verbose) {
    std::cout << "Loaded " << users.size() << " users.\n";
    for (auto& uid : users) 
      std::cout << "  user " << uid << " has " << counts[uid] << " shifts\n";
  }

  std::vector<Assignment> filled; 
  fetch_filled_shifts(db, week, filled); 
  if (verbose) {
    std::cout << "Already filled slots for week " << week << ":\n";
    for (auto& [slot, location, uid] : filled) {
      std::cout << "  slot=" << slot << " location=" << location << "uid=" << uid << '\n';
    }
  }

  // Get highest shift count 
  int max_count = 0;
  const auto pair_compare = [](auto& a, auto& b) {
    return a.second < b.second;
  };

  auto it = std::max_element(counts.begin(), counts.end(), pair_compare);
  max_count = it->second;

  // Container for uids that have been assigned a shift
  std::unordered_set<int> assigned_uids; 
  // Container for already assigned shifts
  std::unordered_set<std::pair<int, std::string>, IntStringHash> assigned;
  // Lookup table for (uid, slot)
  std::unordered_set<std::pair<int, int>, IntIntHash> uid_has_slot; 

  // Fill all three tables 
  for (auto& [slot, location, uid] : filled) {
    assigned.emplace(slot, location);
    assigned_uids.insert(uid);
    uid_has_slot.emplace(uid, slot);
  }

  std::vector<std::pair<int, std::string>> missing; 
  std::vector<int> slots; 

  for (int slot = FIRST_SLOT; slot < TOTAL_SLOTS; slot++)
    slots.push_back(slot);
  for (int slot = 0; slot < LAST_SLOT; slot++)
    slots.push_back(slot);

  int slot_count = slots.size();

  for (int slot : slots) {
    for (auto& location : GENERAL) {
      if (assigned.count({slot, location}) != 0) 
        continue; 

      missing.emplace_back(slot, location);
    }

    for (auto& location : BAR) {
      if (assigned.count({slot, location}) != 0) 
        continue;

      missing.emplace_back(slot, location);
    }
  }
  
  // Split missing by location 
  std::vector<std::pair<int, std::string>> missing_bar, missing_general;
  for (auto& empty_slot : missing) {
    auto [slot, location] = empty_slot;
    bool bar_location = (location == "Bar1" || location == "Bar2");
   
    // Split missing up. Do not push first hour into bar 
    if (bar_location == false) {  
      missing_general.push_back(empty_slot);
    } else {
      bool in_window1 = slot >= FIRST_SLOT + 2;
      bool in_window2 = slot >= 0 && slot < LAST_SLOT;
      if (in_window1 || in_window2) {
        missing_bar.push_back(empty_slot);
      }
    }
  }

  std::unordered_map<int, int> capacity_map; 
  std::vector<int> eligible;

  // Get eligible users
  for (int uid : users) {
    if (assigned_uids.count(uid) == 0) {
      capacity_map[uid] = 2;
      eligible.push_back(uid);
    }
  }

  // Split eligible by location
  std::vector<int> eligible_bar, eligible_general;
  for (int uid : eligible) {
    if (status_map[uid] == "BAR")
      eligible_bar.push_back(uid);
    else 
      eligible_general.push_back(uid);
  }

  std::unordered_map<int, double> weights;
  // Logistic weights
  auto logistic_weight = [&max_count](int count) {
    double x   = static_cast<double>(count) / static_cast<double>(max_count);
    double raw = 1.0 / (1.0 + std::exp(10.0 * (x - 0.5)));
    return std::clamp(raw, tol, 1.0);    // clamp at some small tolerance 
  };

  // Get logistic weights to give advantage to users who have worked more shifts
  for (int uid : eligible) 
    weights[uid] = -std::log(logistic_weight(counts[uid]));
  
  // Build bar manifest first 
  auto bar_manifest = compute_flow(
    slots,
    eligible_bar,
    missing_bar,
    counts,
    capacity_map,
    uid_has_slot,
    weights,
    0.0,
    verbose
  ); 

  // Remove bar workers from pool
  for (auto& assignment : bar_manifest) {
    capacity_map[assignment.user_id]--;
    uid_has_slot.emplace(assignment.user_id, assignment.slot);
  }

  auto general_manifest = compute_flow(
    slots,
    eligible_general,
    missing_general,
    counts,
    capacity_map,
    uid_has_slot,
    weights,
    0.0,
    verbose 
  );

  // Merge the pre-selected manifest with the found manifest 
  filled.insert(
    filled.end(),
    bar_manifest.begin(),
    bar_manifest.end()
  );

  filled.insert(
    filled.end(),
    general_manifest.begin(),
    general_manifest.end()
  );

  // Print final manifest for verbose 
  if (verbose) {
    for (auto &a : filled) {
      std::cout << "slot " << a.slot
                << " @ "   << a.location
                << " → user " << a.user_id << "\n";
    }
  }

  char* errmsg = nullptr; 
  if (sqlite3_exec(db, "BEGIN TRANSACTION;", nullptr, nullptr, &errmsg) != SQLITE_OK) {
    sqlerr(db, errmsg); 
    return 1;
  }

  delete_old_shifts(db, week);
  insert_manifest(db, week, filled);

  if (sqlite3_exec(db, "COMMIT;", nullptr, nullptr, &errmsg) != SQLITE_OK) {
    sqlerr(db, errmsg);
    return 1;
  }

  sqlite3_close(db);
  return 0;
}
