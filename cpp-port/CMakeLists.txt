cmake_minimum_required(VERSION 3.10)
project(cpp_engine CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(cpp_engine
    main.cpp
    position.cpp
    search.cpp
    mcts.cpp
    treenode.cpp
    rc4.cpp
    a.cpp
)
