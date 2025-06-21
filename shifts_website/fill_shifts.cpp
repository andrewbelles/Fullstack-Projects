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
            std::unordered_map<int, int>& counts) 
{
  const char* sql_users = "SELECT id FROM users;";  
  sqlite3_stmt* stmt = nullptr;  
  // Prepare users query
  if (sqlite3_prepare_v2(db, sql_users, -1, &stmt, nullptr) != SQLITE_OK)
    sqlerr(db, "Failed to prepare users query");

  // Pull users from query
  while (sqlite3_step(stmt) == SQLITE_ROW) {
    int uid = sqlite3_column_int(stmt, 0);
    users.push_back(uid);
    counts[uid] = 0;
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

// Cost flow depth first search, to push flow units from vertex u to target 
// Returns the amount that successfully pushed 
int 
dinic_dfs(int u, 
          int target, 
          int flow, 
          std::vector<int>& level, 
          std::vector<int>& iterator, 
          std::vector<std::vector<Edge>>& graph)
{
  // Base case: reached sink and return the pushed flow 
  if (u == target)
    return flow; 

  // Iterate over edges in graph, cache progress in iterator
  for (int& i = iterator[u]; i < int32_t(graph[u].size()); i++) {
    Edge &e = graph[u][i];
    
    // Only advance along edges with capacity and lead closer 
    if (e.capacity > 0 && level[e.to] == level[u] + 1) {
      // Try to push  
      int pushed = dinic_dfs(
        e.to, 
        target, 
        std::min(flow, e.capacity), 
        level, 
        iterator, 
        graph
      );
      
      if (pushed > 0) {
        // Reduce capacity on forward edge 
        e.capacity -= pushed; 
        // Increase capacity on reverse edge
        graph[e.to][e.reverse].capacity += pushed; 
        return pushed; 
      }
    }
  }
  return 0;
}

// DFS helper function. Pushes neighbors of u onto qeue to build level graph 
inline void 
push_vertices(std::vector<std::vector<Edge>>& graph, 
              std::queue<int>& flow_queue, 
              std::vector<int>& level, 
              int u) 
{
    for (auto &edge : graph[u]) {
      // If neighbor hasn't been visited and edge has capacity 
      if (level[edge.to] < 0 && edge.capacity > 0) {
        level[edge.to] = level[u] + 1; 
        flow_queue.push(edge.to);
      }
    }
}

// Returns the maximum flow from source to target 
int 
max_flow(int source, int target, std::vector<std::vector<Edge>>& graph) {
  int flow = 0;
  std::vector<int> level(graph.size()), iterator(graph.size());

  while (true) {

    // Build level graph 
    std::fill(level.begin(), level.end(), -1); 
    std::queue<int> flow_queue; 
    flow_queue.push(source);
    level[source] = 0;
    while (!flow_queue.empty()) {
      int u = flow_queue.front();
      flow_queue.pop();
      push_vertices(graph, flow_queue, level, u);
    }
 
    // Check that sink is reached. If yes, continue augmenting paths  
    if (level[target] < 0)
      break;

    // Find blocking flow in this level graph 
    std::fill(iterator.begin(), iterator.end(), 0);
    while(int pushed = dinic_dfs(
      source, 
      target, 
      std::numeric_limits<int>::max(),
      level, 
      iterator, 
      graph)) 
    { 
      flow += pushed; 
    }
  }
  return flow;
}

// Build manifest based on logistic probability curve. 
// Over time, higher shift count advantage lessens 
void 
build_manifest(std::vector<std::vector<Edge>>& graph,
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
  const int N = eligible_count + missing_count + 2;
  int source = 0;
  int first_user = 1; 
  int first_slot = 1 + eligible_count;
  int sink = N - 1 ;

  // Initialize graph 
  for (int i = 0; i < eligible_count; i++) {
    int uid = eligible[i];

    add_edge(graph, source, first_user + i, capacity_map.at(uid), 0);
  }

  for (int i = 0; i < eligible_count; i++) {
    int uid  = eligible[i];
    int node = first_user + i;
    int raw_cost = int(std::round(smoothing_factor * weights.at(uid) * COST_SCALE));
    for (int j = 0; j < missing_count; j++) {
      int slot = missing[j].first; 
      if (uid_has_slot.count({uid, slot}))
        continue; 

      add_edge(graph, node, first_slot + j, 1, raw_cost);
    }
  }

  for (int j = 0; j < missing_count; j++) {
    add_edge(graph, first_slot + j, sink, 1, 0);
  }
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
                 int first_user,
                 int first_slot)
{
  const int eligible_count(eligible.size());
  const int missing_count(missing.size());

  std::vector<Assignment> result;

  for (int i = 0; i < eligible_count; i++) {
    int uid  = eligible[i];
    int node = first_user + i;

    for (auto& edge : graph[node]) {
      if (edge.to >= first_slot && edge.to < first_slot + missing_count) {
        if (edge.capacity == 0) {
          int slot_idx = edge.to - first_slot;
          auto [slot, location] = missing[slot_idx];
          result.push_back(Assignment(slot, location, uid));
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
  return gini <= 0.25;
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

  fetch_users(db, users, counts); 
  
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

  int missing_slots = missing.size();

  std::unordered_map<int, int> capacity_map; 
  std::vector<int> eligible;

  for (int uid : users) {
    if (assigned_uids.count(uid) == 0) {
      capacity_map[uid] = 2;
      eligible.push_back(uid);
    }
  }

  int eligible_count(eligible.size());
  int missing_count(missing.size());
  int N = 2 + eligible_count + missing_count;
  int source = 0, sink = N - 1, first_user = 1, first_slot = 1 + eligible_count;
  std::vector<std::vector<Edge>> graph(N);

  for (int i = 0; i < eligible_count; i++) 
    add_edge(graph, source, first_user + i, capacity_map[eligible[i]]);


  for (int i = 0; i < eligible_count; i++) {
    int uid = eligible[i];

    for (int j = 0; j < missing_count; j++) {
      int slot = missing[j].first; 
      if (uid_has_slot.count({uid, slot}) != 0)
        continue;

      add_edge(graph, first_user + i, first_slot + j, 1);
    }
  }
  
  for (int j = 0; j < missing_count; j++)
    add_edge(graph, first_slot + j, sink, 1);

  // Assert that there exists a solution
  int flow = max_flow(source, sink, graph);
  if (flow < missing_count) {
    std::ofstream err("logs/error.log");
    err << "Only " << flow << "of " << " slots can be filled\n";
    return 1;
  }

  // Logistic weights
  std::unordered_map<int, double> weights; 
  auto logistic_weight = [&max_count](int count) {
    double x   = static_cast<double>(count) / static_cast<double>(max_count);
    double raw = 1.0 / (1.0 + std::exp(10.0 * (x - 0.5)));
    return std::clamp(raw, tol, 1.0);    // clamp at some small tolerance 
  };

  // Get logistic weights to give advantage to users who have worked more shifts
  for (int uid : eligible) 
    weights[uid] = -std::log(logistic_weight(counts[uid]));

  // Data structure to hold the final manifest of slot, location, uid tuples
  std::vector<Assignment> manifest; 
  for (double smooth_factor = 0.0; smooth_factor <= 1.0 + tol; smooth_factor += 0.1) {
    if (verbose)
      std::cout << "Smoothing Factor: " << smooth_factor << '\n';
    
    // Start with empty graph 
    graph.assign(N, {});

    build_manifest(
      graph, 
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

    // Get matching from cost 
    std::vector<Assignment> matching = extract_matching(
      graph,
      eligible,
      missing,
      first_user,
      first_slot
    ); 

    // Check if fair enough and break early if so 
    if (is_fair(matching, counts)) {
      manifest = std::move(matching);
      break;
    }
  }
  
  // Merge the pre-selected manifest with the found manifest 
  filled.insert(
    filled.end(),
    manifest.begin(),
    manifest.end()
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
