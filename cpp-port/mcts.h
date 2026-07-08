#ifndef MCTS_H
#define MCTS_H
#include "position.h"
#include "treenode.h"
#include <vector>
#include <set>
class Position;

class mcts
{
public:
    //mcts();
    Position *pos;
    mcts(Position *);
    ~mcts();
    std::vector<Treenode*> AllTreeVectorForDestructor;

    unsigned short search(Treenode *);

    Treenode *select(Treenode *);
    Treenode *expand2(Treenode *node);
    Treenode *tree_policy(Treenode *);
    Treenode * best_child(Treenode *);
    unsigned short next_move(Treenode *node);
    //Treenode *next_move(Treenode *);
    float GetUCB(Treenode *,bool);
    Treenode *expand(Treenode *);
    short default_policy();
    Treenode * backup(Treenode *,short );
    unsigned short random_set_element( std::set<unsigned short>& s);
};

#endif // MCTS_H
