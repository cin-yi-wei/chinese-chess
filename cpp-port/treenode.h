#ifndef TREENODE_H
#define TREENODE_H
#include <vector>
#include "position.h"
#include <set>
class Position;

class Treenode
{
public:
    Treenode(unsigned short move, std::set<unsigned short> moves,Treenode *parentnode,std::vector<Treenode*> *Destructor);
    std::set<unsigned short> moves;
    unsigned short move;
     Treenode *parent;
     std::vector< Treenode*> children;
     int wins=0; //節點最終收益價值
     int visits =0; //節點被訪問次數
     bool sdPlayer=0;
     bool leaf=false;
     bool gameover=false;


     bool isLeaf();
     bool is_all_expand(int);
    float GetUCB(float);
    Treenode *select(Treenode);
    Treenode *expand_move(Treenode *node,Position *pos,std::vector< Treenode*> *Destructor);
    unsigned short random_set_element( std::set<unsigned short>& s);


};


#endif // TREENODE_H
