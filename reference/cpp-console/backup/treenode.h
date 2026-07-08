#ifndef TREENODE_H
#define TREENODE_H
#include <QVector>
#include "position.h"
#include <QStack>
#include <QSet>
class Position;

class Treenode
{
public:
    Treenode(unsigned short move, QSet<unsigned short> moves,Treenode *parentnode,QVector<Treenode*> *Destructor);
    QSet<unsigned short> moves;
    unsigned short move;
     Treenode *parent;
     QVector< Treenode*> children;
     int wins=0; //節點最終收益價值
     int visits =0; //節點被訪問次數
     bool sdPlayer=0;
     bool leaf=false;
     bool gameover=false;


     bool isLeaf();
     bool is_all_expand(int);
    float GetUCB(float);
    Treenode *select(Treenode);
    Treenode *expand_move(Treenode *node,Position *pos,QVector< Treenode*> *Destructor);
    unsigned short random_set_element( QSet<unsigned short>& s);


};


#endif // TREENODE_H
