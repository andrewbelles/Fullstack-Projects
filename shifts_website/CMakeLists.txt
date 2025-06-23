cmake_minimum_required(VERSION 3.14)
project(fill_shifts VERSION 1.0 LANGUAGES CXX)

# C++ 17 
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Get postgresql  
find_package(PkgConfig REQUIRED)
pkg_check_modules(PQXX REQUIRED libpqxx)

add_executable(fill_shifts fill_shifts.cpp)

target_include_directories(fill_shifts PRIVATE ${PQXX_INCLUDE_DIRS})
target_link_libraries(fill_shifts PRIVATE ${PQXX_LIBRARIES})
