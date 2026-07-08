#include "search.h"
#include "position.h"
#include <QDebug>
#include "mcts.h"
#include <QDateTime>
Search::Search(Position *Pos)
{
pos=Pos;
}
Search::~Search(){
   // delete searchMain();


    //unsigned short mvResult;
}

// 极大点搜索
short Search::maxSearch(unsigned char depth) {
  // 深度为0，调用评估函数并返回分值
  if (depth == 0)  return this->pos->evaluate2();
/*
  int vlRep = this->pos->repStatus(1);
   if (vlRep > 0) {
     return this->pos->repValue(vlRep);
   }
*/

  short vlBest = - this->pos->MATE_VALUE;				// 初始最优值为负无穷
  QVector< unsigned short> mvs = this->pos->generateMoves();	// 生成当前局面的所有走法
  unsigned short mv = 0;
  short value = 0;
  for (int i = 0; i < mvs.length(); i ++) {
    mv = mvs[i];
    // 执行mv走法
    if (!this->pos->makeMove(mv)) {
      // 这招棋走完后，老将处于被攻击的状态，这是在送死。应该跳过这招棋，继续后面的搜索。
      continue;
    }


    // 调用极小点搜索算法，搜索深度为depth - 1
    value = this->minSearch(depth - 1);

    // 撤销mv走法
    this->pos->undoMakeMove();

    // 寻找最大估值
    if (value > vlBest) {
      // 找到了当前的最佳值
      vlBest = value;

      // 如果回到了根节点，需要记录根节点的最佳走法
      if (depth == MINMAXDEPTH) {
        this->mvResult = mv;
      }
    }
  }

  return vlBest;	// 返回当前节点的最优值
}


short Search::minSearch(unsigned char depth) {
  if (depth == 0) {
    return this->pos->evaluate2();
  }
  short vlBest =  this->pos->MATE_VALUE;				// 初始最优值为正无穷，这里与极大点搜索不同
  QVector< unsigned short> mvs = this->pos->generateMoves();	// 生成当前局面的所有走法
  unsigned short mv = 0;
  short value = 0;

  for (int i = 0; i < mvs.length(); i ++) {
    mv = mvs[i];
    if (!this->pos->makeMove(mv)) {
      continue;
    }
    value = this->maxSearch(depth - 1);	// 这里与极大点搜索不同
    this->pos->undoMakeMove();

    if (value < vlBest) {				// 这里与极大点搜索不同
      vlBest = value;
      if (depth == MINMAXDEPTH) {
        this->mvResult = mv;
      }
    }

  }

  return vlBest;	// 返回当前节点的最优值
}




void Search::maxMinSearch() {
        if (this->pos->sdPlayer == 0) {
          // 红方走棋，调用极大点搜索（因为红方节点是极大点）
          this->maxSearch(Search::MINMAXDEPTH);
        } else {
          // 黑方走棋，调用极小点搜索（因为黑方节点是极小点）
          this->minSearch(Search::MINMAXDEPTH);
        }
      }
short Search::alphaBetaSearch(short vlAlpha_,short vlBeta,int depth) {
  // 深度为0，调用评估函数并返回分值
  if (depth == 0) {
    //   qDebug()<<"evaluate"<<this->pos->evaluate();
    return this->pos->evaluate();
  }
  short vlAlpha = vlAlpha_;				// 初始最优值（不再是负无穷）
/*
  int vlRep = this->pos->repStatus(1);
    if (vlRep > 0) {
      return this->pos->repValue(vlRep);
    }
*/
  QVector< unsigned short> mvs = this->pos->generateMoves();	// 生成当前局面的所有走法
  if(mvs.size()==0) qDebug()<<mvs.size();
  unsigned short mv=0;
  short vl = 0;
  for (int i = 0; i < mvs.length(); i ++) {
    mv = mvs[i];
    // 执行mv走法
    if (!this->pos->makeMove(mv)) {
      // 这招棋走完后，老将处于被攻击的状态，这是在送死。应该跳过这招棋，继续后面的搜索。
      continue;
    }


    if(this->pos->SRC(mv)<129  || this->pos->DST(mv)<129){ //
        this->pos->undoMakeMove();
        continue;
 }

    if( this->pos->repStatus2()==true)
    {
        this->pos->undoMakeMove();
        continue;
    }

    // 递归调用，注意有个负号
    vl = -this->alphaBetaSearch(-vlBeta, -vlAlpha, depth - 1);	// 递归调用，注意有三个负号

    // 撤销mv走法
    this->pos->undoMakeMove();

    // 得到一个大于或等于bate的值，就终止对当前节点的搜索，并返回vlBeta
    if(vl >= vlBeta) {
      return vlBeta;
    }

    // 寻找最大估值
    if (vl > vlAlpha) {
      // 找到了当前的最佳走法
      vlAlpha = vl;

      // 如果回到了根节点，需要记录根节点的最佳走法
      if (this->pos->distance == 0) {
        this->mvResult = mv;
      }
    }
  }

  return vlAlpha;	// 返回当前节点的最优值
}

unsigned short Search::searchMainsecond() { //ALPHA-BETA
  this->mvResult = 0; 	// 搜索出的走法
  this->pos->distance = 0;
  //short vl=0;
  //this->maxMinSearch();	// 调用极大极小搜索算法
  //this->alphaBetaSearch(-pos->MATE_VALUE, pos->MATE_VALUE, MINMAXDEPTH);

    //疊代加深
    qint64 t = QDateTime::currentDateTime().toMSecsSinceEpoch();
    qint64 time_limit=100;
    for (int i = 1; i <= 64; i ++) {
       short vl =this->alphaBetaSearch(-pos->MATE_VALUE, pos->MATE_VALUE, i);
       //this->pos->distance = 0;
            // 已经花费的时间 qDebug();
       if (QDateTime::currentDateTime().toMSecsSinceEpoch() - t > time_limit) {
         break;
       }
       if (vl > pos->WIN_VALUE || vl < -pos->WIN_VALUE) {	// 胜负已分，不用继续搜索
          // qDebug()<<"結束"<<i<<vl<<this->mvResult;
         break;
       }
       //qDebug()<<"times"<<i;
    }

  return this->mvResult;	// 返回搜索结果
}

unsigned short Search::searchMain() { //MCTS
  this->mvResult = 0; 	// 搜索出的走法
  mcts MCTS(this->pos);
  QVector<unsigned short> v=this->pos->generateMoves();
  QSet< unsigned short> set;
  auto t=v.begin();
   while( t!=v.end()){
    set.insert(*t);
    ++t;
   }
  Treenode *root =new Treenode(1333,set,nullptr,&MCTS.AllTreeVectorForDestructor);
  this->mvResult=MCTS.search(root);
  return this->mvResult;	// 返回搜索结果
}

