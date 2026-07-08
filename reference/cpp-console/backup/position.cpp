#include "position.h"
#include <QDebug>
#include<QVector>
#include<QTime>
#include "rc4.h"
Position::Position()
{
    rc4 rc4((unsigned char*) "ab");

    PreGen_zobristKeyPlayer = rc4.nextLong();
    rc4.nextLong();
    PreGen_zobristLockPlayer = rc4.nextLong();
    for (int i = 0; i < 14; i ++) {
      for (int j = 0; j < 256; j ++) {
        PreGen_zobristKeyTable[i][j]=rc4.nextLong();
        rc4.nextLong();
        PreGen_zobristLockTable[i][j]=rc4.nextLong();
      }
    }


}
// 获取走法的起点
unsigned char Position::SRC(unsigned short mv){
    return mv & 255;
}

// 获取走法的终点
unsigned char Position::DST(unsigned short mv){
    return mv >> 8;
}
bool Position::IN_BOARD(unsigned char sq) {
  return IN_BOARD_[sq] != 0;
}
bool Position::IN_FORT(unsigned char sq) {
  return IN_FORT_[sq] != 0;
}
bool Position::KING_SPAN(unsigned char sqSrc, unsigned char sqDst) {
  return LEGAL_SPAN[sqDst - sqSrc + 256] == 1;
}
bool Position::HOME_HALF(unsigned char sq,bool sd) {
  return (sq & 0x80) != (sd << 7);
}

bool Position::ADVISOR_SPAN(unsigned char sqSrc, unsigned char sqDst) {
  return LEGAL_SPAN[sqDst - sqSrc + 256] == 2;
}

bool Position:: BISHOP_SPAN(unsigned char sqSrc,unsigned char  sqDst) {
  return LEGAL_SPAN[sqDst - sqSrc + 256] == 3;
}

// 象眼的位置
unsigned char Position:: BISHOP_PIN(unsigned char  sqSrc,unsigned char  sqDst) {
//  return (sqSrc + sqDst) /2;
  return (sqSrc + sqDst) >> 1;
}

unsigned char Position::KNIGHT_PIN(unsigned char sqSrc,unsigned char sqDst) {
  return sqSrc + this->KNIGHT_PIN_[sqDst - sqSrc + 256];
}

bool Position::AWAY_HALF(unsigned char sq,bool sd) {
  return (sq & 0x80) == (sd << 7);
}

// 如果从起点sqSrc到终点sqDst没有过河，则返回true；否则返回false
bool Position:: SAME_HALF(unsigned char sqSrc, unsigned char sqDst) {
  return ((sqSrc ^ sqDst) & 0x80) == 0;
}

// 如果sqSrc和sqDst在同一行则返回true，否则返回false
bool Position:: SAME_RANK(unsigned char sqSrc, unsigned char sqDst) {
  return ((sqSrc ^ sqDst) & 0xf0) == 0;
}

// 如果sqSrc和sqDst在同一列则返回true，否则返回false
bool Position:: SAME_FILE(unsigned char sqSrc, unsigned char sqDst) {
  return ((sqSrc ^ sqDst) & 0x0f) == 0;
}
// sp是棋子位置，sd是走棋方（红方0，黑方1）。返回兵（卒）向前走一步的位置。
unsigned char Position::SQUARE_FORWARD(unsigned char sq,bool sd) {
  return sq - 16 + (sd << 5);
}

unsigned short Position::MOVE(unsigned char sqSrc, unsigned char sqDst){

    return sqSrc + (sqDst << 8);
}

unsigned char Position::SIDE_TAG(unsigned char sd) {
 // unsigned char a=sd? 1:0;
  return 8 + (sd << 3);
}
unsigned char Position::OPP_SIDE_TAG(unsigned char sd) {
  return 16 - (sd << 3);
}
void Position::setIrrev() {

    this->mvList.push(0);	// 存放每步走法的数组
  this->pcList.push(0);	// 存放每步被吃的棋子。如果没有棋子被吃，存放的是0

  this->distance = 0;	// 步数

}

void Position::movePiece(unsigned short mv) {
  unsigned char sqSrc = SRC(mv);			// 起点位置
  unsigned char sqDst = DST(mv);			// 终点位置
  unsigned char pc = this->squares[sqDst];	// 终点位置的棋子
  this->pcList.push(pc);			// 将终点位置的棋子，存入吃子列表
  if (pc > 0) {
    // 终点有棋子，则要删除该棋子
    this->addPiece(sqDst, pc, DEL_PIECE);
  }
  pc = this->squares[sqSrc];
  this->addPiece(sqSrc, pc, DEL_PIECE);	// 删除起点棋子
  this->addPiece(sqDst, pc, ADD_PIECE);	// 将原来起点的棋子添加到终点
  this->mvList.push(mv);					// 将走法存入走法列表
}
void Position::undoMovePiece() {
  unsigned short mv = this->mvList.pop();
  unsigned char sqSrc = SRC(mv);
  unsigned char sqDst = DST(mv);
  unsigned char pc = this->squares[sqDst];
  this->addPiece(sqDst, pc, DEL_PIECE);	// 删除终点棋子
  this->addPiece(sqSrc, pc, ADD_PIECE);	// 将终点位置的棋子添加到起点
  pc = this->pcList.pop();
  if (pc > 0) { // 这步棋发生了吃子，需要把吃掉的棋子放回终点位置
    this->addPiece(sqDst, pc, ADD_PIECE);
  }
}
void Position::changeSide() {
  this->sdPlayer = ! this->sdPlayer;

}

void Position::makeMove2 (unsigned short mv) {
  this->movePiece(mv);		// 移动棋子
  this->changeSide();		// 切换走棋方
  this->distance ++;			// 棋局深度+1

}

bool Position::makeMove (unsigned short mv) {
  this->movePiece(mv);		// 移动棋子
  // 检查走棋是否被将军。如果是，说明这是在送死，撤销走棋并返回false。
  if (this->checked()) {
    this->undoMovePiece();	// 撤销棋子移动
    return false;
  }
  this->keyList.push(this->zobristKey);		// 存储局面的zobristKey校验码
  this->changeSide();		// 切换走棋方
  this->chkList.push(this->checked());
  this->distance ++;			// 棋局深度+1
  return true;
}
void Position::undoMakeMove() {
        this->distance --;	// 棋局深度减1
        this->chkList.pop();
        this->changeSide();	// 切换走棋方
        this->keyList.pop();
        this->undoMovePiece();	// 取消上一步的走棋
      }

bool Position::legalMove (unsigned short mv){

    unsigned char sqSrc = SRC(mv);						// 获取走法的起点位置
      unsigned char pcSrc = this->squares[sqSrc];			// 获取起点位置的棋子
      unsigned char pcSelfSide = SIDE_TAG(this->sdPlayer? 1:0);	// 红黑标记(红子是8，黑子是16)

      if ((pcSrc & pcSelfSide) == 0) {
        // 起点位置的棋子，不是本方棋子。（是对方棋子，或者根本没有棋子）
          qDebug()<<"NOOOOOOOOO";
           qDebug()<<"RANDOM位置"<<mv<<(int)(SRC(mv)/16)-3<<(SRC(mv)%16)-3<<(int)(DST(mv)/16)-3<<(DST(mv)%16)-3;
        return false;
      }

      unsigned char sqDst = DST(mv);				// 获取走法的终点位置
      unsigned char pcDst = this->squares[sqDst];	// 获取终点位置的棋子

      if ((pcDst & pcSelfSide) != 0) {
        // 终点位置有棋子，而且是本方棋子
        return false;
      }

      switch (pcSrc - pcSelfSide) {
      case Position::PIECE_KING:{		// 起点棋子是将（帅），校验走法
        return this->IN_FORT(sqDst) && this->KING_SPAN(sqSrc, sqDst);}
      case Position::PIECE_ADVISOR:{	// 起点棋子是仕（仕），校验走法
        return this->IN_FORT(sqDst) && this->ADVISOR_SPAN(sqSrc, sqDst);}
      case Position::PIECE_BISHOP:{	// 起点棋子是象（相），校验走法
        return this->SAME_HALF(sqSrc, sqDst) && this->BISHOP_SPAN(sqSrc, sqDst) &&
            this->squares[this->BISHOP_PIN(sqSrc, sqDst)] == 0;}
      case Position::PIECE_KNIGHT:{	// 起点棋子是马，校验走法
        unsigned char sqPin = this->KNIGHT_PIN(sqSrc, sqDst);
        return sqPin != sqSrc && this->squares[sqPin] == 0;
        }
      case Position::PIECE_ROOK:		// 起点棋子是车，校验走法
      case Position::PIECE_CANNON:{	// 起点棋子是炮，校验走法
        char delta;			// 标识沿哪个方向走棋
        if (this->SAME_RANK(sqSrc, sqDst)) {
          // 起点和终点位于同一行。再根据起点和终点的大小关系，判断具体是沿哪个方向走棋。
          delta = (sqDst < sqSrc ? -1 : 1);
        } else if (this->SAME_FILE(sqSrc, sqDst)) {
          // 起点和终点位于同一列。再根据起点和终点的大小关系，判断具体是沿哪个方向走棋。
          delta = (sqDst < sqSrc ? -16 : 16);
        } else {
          // 起点和终点不在同一行，也不在同一列。走法是非法的。
          return false;
        }
        unsigned char sqPin = sqSrc + delta;	// 沿着方向delta走一步棋
        while (sqPin != sqDst && this->squares[sqPin] == 0) {
          // 沿方向delta一步步向前走，直到遇到棋子，或者sqPin走到了终点的位置上
          sqPin += delta;
        }
        if (sqPin == sqDst) {
          // 如果终点没有棋子，不管是车还是炮，这步棋都是合法的。如果是车，不管终点有没有棋子（对方棋子），这步棋都合法。
          return pcDst == 0 || pcSrc - pcSelfSide == PIECE_ROOK;
        }
        // 此时已经翻山，终点必须有棋子，并且行棋的是炮，否则这步棋不合法
        if (pcDst == 0 || pcSrc - pcSelfSide != PIECE_CANNON) {
          return false;
        }
        sqPin += delta;
        while (sqPin != sqDst && this->squares[sqPin] == 0) {
          sqPin += delta;
        }
        return sqPin == sqDst;}
      case Position::PIECE_PAWN:{
        // 兵已过河，并且是左右两个方向走的
        if (this->AWAY_HALF(sqDst, this->sdPlayer) && (sqDst == sqSrc - 1 || sqDst == sqSrc + 1)) {
          return true;
        }
        // 判断兵是不是在向前走
        return sqDst == this->SQUARE_FORWARD(sqSrc, this->sdPlayer);}
      default:
        return false;
      }
}

bool Position::checked() {
    unsigned char pcSelfSide = SIDE_TAG(this->sdPlayer);		// 己方红黑标记
    unsigned char pcOppSide = OPP_SIDE_TAG(this->sdPlayer);	// 对方红黑标记
  for (int sqSrc = 0; sqSrc < 256; sqSrc ++) {
    // 遍历棋局数组，直到遇见己方的将（帅）
    if (this->squares[sqSrc] != pcSelfSide + PIECE_KING) {
      continue;
    }

    // 判断对方进兵，是否会攻击到己方老将
    if (this->squares[SQUARE_FORWARD(sqSrc, this->sdPlayer)] == pcOppSide + PIECE_PAWN) {
      return true;
    }
    // 判断对方平兵（前提是并已过河），是否会攻击到己方老将
    for (int delta = -1; delta <= 1; delta += 2) {
      if (this->squares[sqSrc + delta] == pcOppSide + PIECE_PAWN) {
        return true;
      }
    }

    // 判断对方马是否攻击到己方老将
    for (int i = 0; i < 4; i ++) {
      if (this->squares[sqSrc + ADVISOR_DELTA[i]] != 0) {	// 马蹄有子，不用害怕哦
        continue;
      }
      for (int j = 0; j < 2; j ++) {
        unsigned char pcDst = this->squares[sqSrc + KNIGHT_CHECK_DELTA[i][j]];
        if (pcDst == pcOppSide + PIECE_KNIGHT) {
          return true;
        }
      }
    }

    // 判断对方的车、炮是攻击到了己方老将，以及将帅是否对脸
    for (int i = 0; i < 4; i ++) {
      char delta = KING_DELTA[i];
      unsigned char sqDst = sqSrc + delta;
      while (this->IN_BOARD(sqDst)) {
        unsigned char pcDst = this->squares[sqDst];
        if (pcDst > 0) {
          if (pcDst == pcOppSide + PIECE_ROOK || pcDst == pcOppSide + PIECE_KING) {	// 对方车能攻击己方老将，或者将帅对脸。
            return true;
          }
          break;
        }
        sqDst += delta;
      }
      sqDst += delta;
      while (IN_BOARD(sqDst)) {
        unsigned char pcDst = this->squares[sqDst];
        if (pcDst > 0) {
          if (pcDst == pcOppSide + PIECE_CANNON) {
            return true;
          }
          break;
        }
        sqDst += delta;
      }
    }
    return false;
  }
  return false;
}


bool Position::isMate() {
   QVector<unsigned short> mvs = this->generateMoves();
  for (int i = 0; i < mvs.length(); i ++) {
    if (this->makeMove(mvs[i])) {
      this->undoMakeMove();
      return false;
    }
  }
  return true;
}


void Position::clearBoard(){
    this->sdPlayer = 0;	// 该谁走棋。0-红方；1-黑方
      for (int sq = 0; sq < 256; sq ++) {
        this->squares[sq]=0;
      }
      this->zobristKey = this->zobristLock = 0;
      this->vlWhite = this->vlBlack = 0;
}
void Position::addPiece(unsigned int sq,unsigned char pc,bool bDel) {
    unsigned char pcAdjust;
    this->squares[sq] = bDel ? 0 : pc;
    if (pc < 16) { //紅旗
      pcAdjust = pc - 8;
      this->vlWhite += bDel ? -this->PIECE_VALUE[pcAdjust][sq] :
          this->PIECE_VALUE[pcAdjust][sq];
    } else {
      pcAdjust = pc - 16;
      this->vlBlack += bDel ? -this->PIECE_VALUE[pcAdjust][254 -sq ] : this->PIECE_VALUE[pcAdjust][254 -sq];
      pcAdjust += 7;
    }
    this->zobristKey ^= this->PreGen_zobristKeyTable[pcAdjust][sq];
    this->zobristLock ^= this->PreGen_zobristLockTable[pcAdjust][sq];
}
unsigned int Position::COORD_XY(unsigned char x,unsigned char y){
    return x + (y << 4);

}

unsigned char Position::CHAR_TO_PIECE(char c) {
  switch (c) {
  case 'K':
    return this->PIECE_KING;
  case 'A':
    return this->PIECE_ADVISOR;
  case 'B':
    return this->PIECE_BISHOP;
  case 'N':
    return this->PIECE_KNIGHT;
  case 'R':
    return this->PIECE_ROOK;
  case 'C':
    return this->PIECE_CANNON;
  case 'P':
    return this->PIECE_PAWN;
  default:
    return -1;
  }
}

void Position::fromFen(std::string fen){
    this->clearBoard();

        unsigned char y = this->RANK_TOP;
        unsigned char x = this->FILE_LEFT;
        unsigned char index = 0;
        if (index == fen.length()) {
            this->setIrrev();
            return;
          }
        char c = fen[index];
        while (c != ' ') {
          if (c == '/') {
            x = this->FILE_LEFT;
            y ++;
            if (y > this->RANK_BOTTOM) {
              break;
            }
          } else if (c >= '1' && c <= '9') {
            x += (int)c-48;
          } else if (c >= 'A' && c <= 'Z') {
            if (x <= this->FILE_RIGHT) {
              unsigned char pt = CHAR_TO_PIECE(c);
              if (pt >= 0) {
                this->addPiece(COORD_XY(x, y), pt + 8, false);
              }
              x ++;
            }
          } else if (c >= 'a' && c <= 'z') {
            if (x <= this->FILE_RIGHT) {
              unsigned char pt = CHAR_TO_PIECE(char((int)c -32));
              if (pt >= 0) {
                this->addPiece(COORD_XY(x, y), pt + 16, false);
              }
              x ++;
            }
          }
          index ++;
          if (index == fen.length()) {
              this->setIrrev();
            return;
          }
          c = fen[index];
        }
        index ++;
        if (index == fen.length()) {
            this->setIrrev();
          return;
        }
        this->setIrrev();
}
short Position::evaluate2() {

  short vl = this->vlWhite - this->vlBlack;
  return vl;
 }
short Position::evaluate() {
    /*
  short vl = this->vlWhite - this->vlBlack;
  return vl;
  if(this->sdPlayer!=false) return vl; else return -vl;//negamax才變
  */
  short vl = (this->sdPlayer == 0 ? (this->vlWhite - this->vlBlack ):(this->vlBlack - this->vlWhite));
  return vl;

}

unsigned short Position::get_next_move_with_random_choice(){

//    QTime t;
//    t= QTime::currentTime();
//    qsrand(t.msec()*1000);

  int length=this->generateMoves().length();
   qDebug()<<"total"<< length ;
  int random= qrand()%(length);
   // qDebug()<<random;


  return this->generateMoves()[random];

}
QVector< unsigned short> Position::generateMoves () {
  QVector< unsigned short> mvs;									// 用于存储所有合法的走法
  unsigned char pcSelfSide = SIDE_TAG(this->sdPlayer);		// 本方红黑标记(红子是8，黑子是16)
  unsigned char pcOppSide = OPP_SIDE_TAG(this->sdPlayer);	// 对方红黑标记(红子是16，黑子是8)
  for (int sqSrc = 0; sqSrc < 256; sqSrc ++) {
    // 遍历虚拟棋盘的256个点

    unsigned char pcSrc = this->squares[sqSrc];		// 某个位置上的棋子
    if ((pcSrc & pcSelfSide) == 0) {		// 这是对方棋子，或者该位置根本没有棋子
      continue;
    }
    switch (pcSrc - pcSelfSide) {
    case PIECE_KING:
      for (int i = 0; i < 4; i ++) {		// 将的4个方向
        unsigned char sqDst = sqSrc + KING_DELTA[i];	// 得到一个可能的终点位置
        if (!IN_FORT(sqDst)) {				// 该位置不位于九宫中，不合法
          continue;
        }
        unsigned char pcDst = this->squares[sqDst];	// 获得终点位置棋子
        if ((pcDst & pcSelfSide) == 0) {	// 终点位置的棋子不是本方棋子，或者终点根本没有棋子
          mvs.push_back(MOVE(sqSrc, sqDst));		// 步骤合法，保存到数组中
        }
      }
      break;
    case PIECE_ADVISOR:
      for (int i = 0; i < 4; i ++) {		// 仕的4个方向
        unsigned char sqDst = sqSrc + ADVISOR_DELTA[i];	// 得到一个可能的终点位置
        if (!IN_FORT(sqDst)) {				// 该位置不位于九宫中，不合法
          continue;
        }
        unsigned char pcDst = this->squares[sqDst];	// 获得终点棋子
        if ((pcDst & pcSelfSide) == 0) {	// 终点位置的棋子不是本方棋子，或者终点根本没有棋子
          mvs.push_back(MOVE(sqSrc, sqDst));		// 步骤合法，保存到数组中
        }
      }
      break;
    case PIECE_BISHOP:
      for (int i = 0; i < 4; i ++) {		// 象的4个方向
        unsigned char sqDst = sqSrc + ADVISOR_DELTA[i];	// 获得象眼的位置
        if (!(IN_BOARD(sqDst) && HOME_HALF(sqDst, this->sdPlayer) &&
            this->squares[sqDst] == 0)) {	//	象眼不在棋盘上，或者象眼位置已过河，或者象眼存在棋子
          continue;
        }
        sqDst += ADVISOR_DELTA[i];			// 得到一个可能的终点位置
        unsigned char pcDst = this->squares[sqDst];	// 得到终点位置的棋子
        if ((pcDst & pcSelfSide) == 0) {	// 终点位置没有本方棋子
          mvs.push_back(MOVE(sqSrc, sqDst));		// 步骤合法，保存到数组
        }
      }
      break;
    case PIECE_KNIGHT:
      for (int i = 0; i < 4; i ++) {		// 马腿的4个方向
        unsigned char sqDst = sqSrc + KING_DELTA[i];	// 得到一个马腿的位置
        if (this->squares[sqDst] > 0) {		// 马腿位置存在棋子
          continue;
        }
        for (int j = 0; j < 2; j ++) {		// 1个马腿对应2个马的方向
          sqDst = sqSrc + KNIGHT_DELTA[i][j];	// 得到一个可能的终点位置
          if (!IN_BOARD(sqDst)) {			// 该位置不在棋盘上
            continue;
          }
          unsigned char pcDst = this->squares[sqDst];	// 得到终点位置的棋子
          if ((pcDst & pcSelfSide) == 0) {	// 终点位置不存在本方棋子
            mvs.push_back(MOVE(sqSrc, sqDst));
          }
        }
      }
      break;
    case PIECE_ROOK:
      for (int i = 0; i < 4; i ++) {
        char delta = KING_DELTA[i];	// 得到一个方向
        unsigned char sqDst = sqSrc + delta;	// 从起点sqSrc开始，沿着方向delta走一步
        while (IN_BOARD(sqDst)) {	// 得到的终点位于棋盘
          unsigned char pcDst = this->squares[sqDst];
          if (pcDst == 0) {			// 终点没有棋子，走法合法
            mvs.push_back(MOVE(sqSrc, sqDst));
          } else {
            if ((pcDst & pcOppSide) != 0) {	// 终点有对方棋子，走法合法
              mvs.push_back(MOVE(sqSrc, sqDst));
            }
            break;
          }
          sqDst += delta;			// 沿着方向delta向前走一步
        }
      }
      break;
    case PIECE_CANNON:
      for (int i = 0; i < 4; i ++) {
        char delta = KING_DELTA[i];	// 得到一个方向
        unsigned char sqDst = sqSrc + delta;	// 从起点sqSrc开始，沿着方向delta走一步
        while (IN_BOARD(sqDst)) {	// 得到的终点位于棋盘
          unsigned char pcDst = this->squares[sqDst];
          if (pcDst == 0) {			// 终点没有棋子，走法合法
            mvs.push_back(MOVE(sqSrc, sqDst));
          } else {
            // 终点存在棋子，炮需要翻山
            break;
          }
          sqDst += delta;			// 沿着方向delta向前走一步
        }
        sqDst += delta;				// 沿着方向delta向前走一步
        while (IN_BOARD(sqDst)) {	// 如果sqDst仍位于棋盘，那么此时炮已经翻山了
          unsigned char pcDst = this->squares[sqDst];
          if (pcDst > 0) {			// 炮翻山后遇到了一个棋子
            if ((pcDst & pcOppSide) != 0) {	// 炮翻山后，遇到的是一个对方棋子
              mvs.push_back(MOVE(sqSrc, sqDst));
            }
            break;					// 炮翻山后，不管遇到的是对方棋子，还是己方棋子，都要结束对当前方向的搜索
          }
          sqDst += delta;
        }
      }
      break;
    case PIECE_PAWN:
      unsigned char sqDst = SQUARE_FORWARD(sqSrc, this->sdPlayer);	// 得到兵前进一步的位置
      if (IN_BOARD(sqDst)) {							// 该位置在棋盘上
        unsigned char pcDst = this->squares[sqDst];
        if ((pcDst & pcSelfSide) == 0) {				// 目标位置没有本方棋子
          mvs.push_back(MOVE(sqSrc, sqDst));
        }
      }
      if (AWAY_HALF(sqSrc, this->sdPlayer)) {			// 这个兵已过河
        for (int delta = -1; delta <= 1; delta += 2) {	// delta只能取-1和1两个值，这是兵的左右两个方向
          sqDst = sqSrc + delta;
          if (IN_BOARD(sqDst)) {						// 该位置在棋盘上
            unsigned char pcDst = this->squares[sqDst];
            if ((pcDst & pcSelfSide) == 0) {			// 目标位置没有本方棋子
              mvs.push_back(MOVE(sqSrc, sqDst));
            }
          }
        }
      }
      break;
    }
  }
  return mvs;
}
bool Position::repStatus2() {
int index = this->mvList.length();
if(index>=13){
    index = this->mvList.length()-5;
    if (this->mvList[index] == this->zobristKey) return true;

    index = this->mvList.length() - 9;
    if (this->mvList[index] == this->zobristKey) return true;

    index = this->mvList.length() - 13;
    if (this->mvList[index] == this->zobristKey) return true;
}else return  false;
index = this->keyList.length();
if(index>=13){
    index = this->keyList.length() - 5;
    if (this->keyList[index] == this->zobristKey) return true;

    index = this->keyList.length() - 9;
    if (this->keyList[index] == this->zobristKey) return true;

    index = this->keyList.length() - 13;
    if (this->keyList[index] == this->zobristKey) return true; else return  false;
}else return  false;
}

int Position::repStatus(int recur_) {
  int recur = recur_;
  bool selfSide = false;
  bool perpCheck = true;
  bool oppPerpCheck = true;
  int index = this->mvList.length() - 1;
  while (this->mvList[index] > 0 && this->pcList[index] == 0) {
    if (selfSide) {
      perpCheck = perpCheck && this->chkList[index];
      if (this->keyList[index] == this->zobristKey) {	// 这是出现循环局面了
        recur --;
        if (recur == 0) {
          return 1 + (perpCheck ? 2 : 0) + (oppPerpCheck ? 4 : 0);
        }
      }
    } else {
      oppPerpCheck = oppPerpCheck && this->chkList[index];
    }
    selfSide = !selfSide;
    index --;
  }
  return 0;
}

 short Position::repValue(int vlRep) {
  short vlReturn = ((vlRep & 2) == 0 ? 0 : this->banValue()) +
      ((vlRep & 4) == 0 ? 0 : -this->banValue());
  return vlReturn == 0 ? this->drawValue() : vlReturn;
}
 short Position::banValue() {
   return this->distance - BAN_VALUE;
 }
 short Position::drawValue() {
   return (this->distance & 1) == 0 ? -DRAW_VALUE : DRAW_VALUE;
 }

