#include "mcts.h"
#include "position.h"
#include "float.h"
#include "math.h"
#include <algorithm>
#include <string>
#include <vector>
#include <cstdlib>
#include <ctime>
//22 68c行 紀錄步數 可以debug
mcts::mcts(Position *Pos)
{
pos=Pos;

}
mcts::~mcts(){


}


unsigned short mcts::search(Treenode *node){
        srand((unsigned int)time(nullptr));

        int computation_budget = 10000;
        for(int i=0;i<computation_budget;i++){
        node =select(node);


        node=expand2(node);
        if(node->gameover==true){
            while (node->parent!= nullptr ){
             this->pos->undoMakeMove(); //原本不用加if
            node = node->parent;
           }
            break;
        }
        short result =default_policy();
        node=backup(node, result);

    }

    return  next_move(node);


}
Treenode *mcts:: select(Treenode *node){
        while( (node->moves.empty() == true) /* && (node->children.length()==this->pos->generateMoves().length())*/ ){
          /*  if(node->children.length()==0 ){
                do{
                    node=node->parent;
                    this->pos->undoMakeMove();
                    qDebug()<<"bug";

                }while (node->parent!= nullptr );


            }*/
            node =best_child(node);
            //if(node->children.length()==0)
        //qDebug()<<"IN_BEST";
            //要加上 makemove2();
           // qDebug()<<"select";
        }
        return node;
}
Treenode *mcts::best_child(Treenode *node){
    //QVector<float> weights;
    int max_index=0;
    float temp,max=FLT_MIN;
   // qDebug()<< "best_child1";

    for(int i=0;i< node->children.size();i++){
      //  if(node->children[i]->leaf==true) continue;
        temp=GetUCB(node->children[i],false);
        //qDebug()<<i<<temp;
        if (temp> max){
            max=temp;
            max_index=i;
            //qDebug()<<"HERE";
        }
    }

    /*
    float *ucb=new float[node->children.length()];
    for(int i=0;i<node->children.length();i++) *(ucb+i)=GetUCB(node->children[i],false);
    std::sort(ucb,ucb+node->children.length(), std::greater<float>());
*/
   // std::sort(node->children.begin(), node->children.end());  //這邊還沒使用getucb
    //qDebug()<< *ucb  << *(ucb+sizeof (float)) ;
    //node->children
    //qDebug()<< this->pos->SRC(node->move)<<this->pos->DST(node->move) ;
   // qDebug()<<"makeMove1"<<pos->generateMoves().length();
//    qDebug()<<node->children.length()<<max_index;
    /*
    while ( !this->pos->makeMove(max_index)){
        max_index++;
    }
    */
   //這邊要作排序
   // qDebug()<<"makeMove2"<<pos->generateMoves().length();
   // qDebug()<< "best_child2"<<max_index<<max ;
    this->pos->makeMove(max_index);
    return node->children[max_index];
}

unsigned short mcts::next_move(Treenode *node){
    //QVector<float> weights;
    int max_index=0;
    float temp,max=FLT_MIN;
   // qDebug()<< "best_child1";
    for(int i=0;i< node->children.size();i++){
        if(node->children[i]->leaf==true) continue;
        temp=GetUCB(node->children[i],true);
        //qDebug()<<i<<temp;
        if (temp> max){
            max=temp;
            max_index=i;
            //qDebug()<<"HERE";
        }
    }


    unsigned short next_move=node->children[max_index]->move;
    //qDebug()<<"AllTreeVectorForDestructor"<< AllTreeVectorForDestructor.size() ;
     std::vector<Treenode *>::iterator iter;
     for (iter=AllTreeVectorForDestructor.begin();iter!=AllTreeVectorForDestructor.end();iter++)
        {
         delete *iter ;
        } //殺80000點

return  next_move;
   // return node->children[max_index];
}


float mcts::GetUCB(Treenode *node,bool next){
    float w;
    if(next) w=((float)(node->wins)/(float)(node->visits));
    else w=((float)(node->wins)/(float)(node->visits)) + sqrt(2.0*log(( (float) (node->parent->visits) /(float)(node->visits))));

    //qDebug()<<node->visits ;
    return w;
}
Treenode *mcts::expand2(Treenode *node){
  return node->expand_move(node,this->pos,&AllTreeVectorForDestructor);
}

short mcts::default_policy(){
 //qDebug()<<this->pos->evaluate() ;
    short now =this->pos->evaluate();
    this->pos->undoMakeMove();
    short prev =this->pos->evaluate();
//6666
    return now-prev;
 //return (this->pos->evaluate()>0) ?true:false;  原本
}
Treenode *mcts::backup(Treenode *node,short reward){
    Treenode *current=node;
    // qDebug()<<current->move;
 int i=0;
 //蒙特卡洛树搜索的Backpropagation阶段，输入前面获取需要expend的节点和新执行Action的reward，反馈给expend节点和上游所有节点并更新对应数据。
 // Update util the root node
do{
   //  qDebug()<<"in";
   //   qDebug()<<"times"<<i;
     //current->test=true;
   // Update the visit times
    // qDebug()<<"visits1"<<node->visits;
   //current->visits+=abs(reward);
   current->visits+=1;
   //qDebug()<<"visits2"<<node->visits;
   // Update the quality value
  // if(reward==)
    if(this->pos->sdPlayer==(reward>0)) { //if(this->pos->sdPlayer==reward) 原
        //贏
//        current->wins+=reward ;
        current->wins+=1 ; //原
    }
    else {
        //輸
       // current->wins-=reward ;//0;
        current->wins+=0; //原
    }

    if(i>0) this->pos->undoMakeMove(); //原本不用加if
   // if(current->root== true) qDebug()<<"true"<<i;
    current = current->parent;

   // Change the node to the parent node
    i++;
   } while (current->parent!= nullptr );
     current->visits+=1;
 return current;
 // while (!this->pos->mvList.empty() ) this->pos->undoMakeMove();
}





