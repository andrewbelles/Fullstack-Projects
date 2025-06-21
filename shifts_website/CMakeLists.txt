cmake_minimum_required(VERSION 3.14)
project(fill_shifts VERSION 1.0 LANGUAGES CXX)

# C++ 17 
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Get sqlite 
find_package(SQLite3 REQUIRED)

add_executable(fill_shifts fill_shifts.cpp)

target_include_directories(fill_shifts PRIVATE ${SQLite3_INCLUDE_DIRS})
target_link_libraries(fill_shifts PRIVATE ${SQLite3_LIBRARIES})
