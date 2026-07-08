#include "treenode.h"
#include "position.h"
#include "math.h"
#include "float.h"
#include <QDebug>
Treenode::Treenode(unsigned short move, QSet<unsigned short> moves,Treenode *parentnode,QVector<Treenode*> *Destructor)
{
    this->move=move;
    this->moves=moves;    //this->unreach=this->pos->generateMoves();
    this->parent=parentnode;
    this->children={};
    this->wins =0; //節點最終收益價值
    this->visits =0; //節點被訪問次數
}
/*
Treenode *Treenode::addchild( ){
       Treenode node = TreeNode( state, parent_action, child_player);
       this->unreach.erase(parent_action);
       children.append(node);
       return &node;
}
*/

bool Treenode::isLeaf() {
    if (this->children.length() == 0) return true;
    else return false;
  }
bool Treenode::is_all_expand( int move_length ) {
   // qDebug()<< this->children.length() << this->children.size() <<this->children.count() ;

    if( this->children.length() == move_length ) return true;
    else return false;
    /*
    for (int i=0;i<this->children.length();i++) {
        if(&this->children.operator[](i).children==nullptr) return false;
     }
     return true;
*/
}

unsigned short Treenode::random_set_element( QSet<unsigned short>& s){
    int r = rand() % s.size();
   // qDebug()<<s.size()<<r;
      QSet<unsigned short>::iterator it = s.begin();
      for (; r != 0; r--) it++;
      //qDebug()<< *it ;
      return *it;
}

Treenode *Treenode::expand_move(Treenode *node,Position *pos,QVector<Treenode*> *Destructor){
    unsigned short move= random_set_element(node->moves);
    this->moves.remove(move);
    //qDebug()<<"makeMove1"<<pos->generateMoves().length();
    // if(!pos->isMate() && !(v.length()==0)){
    int i=0;
    int times=0;
    int all_moves_count=node->moves.size();
    while (! pos->makeMove(move)  ){ //將軍
 if(times==all_moves_count ){node->gameover=true; return node;}
        //qDebug()<<"將軍"<<pos->evaluate()<<pos->sdPlayer<<++i<<node->moves.size() ;
        move= random_set_element(node->moves);
         this->moves.remove(move);
        times++;

        //if(node->moves.size()==0){node->leaf=true; return nullptr; }
    }
        QVector<unsigned short> v=pos->generateMoves();
       QSet< unsigned short> set;
       auto t=v.begin();
        while( t!=v.end()){
         set.insert(*t);
         ++t;
        }
          // if ( !(v.length()==set.size()))  qDebug()<<"length";
          //  qDebug()<<"length"<<v.length();
        Treenode *sub_node =new Treenode(move,set,node,Destructor);  //this?????????????????????????
        this->children.append(sub_node);
        Destructor->append(sub_node);
    /*
        if(set.size()==0){
            sub_node->leaf=true;
            qDebug()<<"game is over";
            //return nullptr;
        }*/

        return sub_node;


   //  }else { pos->undoMakeMove();  return nullptr;}
}
