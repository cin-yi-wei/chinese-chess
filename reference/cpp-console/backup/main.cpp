#include <QCoreApplication>
#include "search.h"
#include "position.h"
#include "string"
#include <QString>
#include "mcts.h"
#include <QDebug>
#include<sstream>
#include "rc4.h"
#include <QStack>
bool alpha_beta();
bool mctss();
bool random2();
bool user1();
void show1();
Position position1;
int main(int argc, char *argv[])
{
    QCoreApplication a(argc, argv);

    //---------------------init
    //    position1.fromFen("1nbakabn1/9/1c5c1/p1p1p1p1p/9/9/9/9/4K3r/8r w - - 0 1");
        //position1.fromFen("rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1");
        // position1.fromFen("2bakab2/9/4c1n2/p3p1p1p/P1p6/5nP2/3r4P/4B3R/4r4/1cBA1K1NR w - - 0 1");
        position1.fromFen("4k4/1c5c1/9/1c5c1/9/r6c1/6P2/4BA3/1R1K5/8n w - - 0 1");
        position1.chkList.push(position1.checked());
        qDebug()<< position1.evaluate() << position1.sdPlayer;
    //    position1.legalMove(position1.MOVE(183,167));
    //    position1.makeMove(position1.MOVE(183,167));
        position1.legalMove(position1.MOVE(153,137));
        position1.makeMove(position1.MOVE(153,137));
        qDebug()<< position1.evaluate2() << position1.sdPlayer;
       // ui->textEdit->setText(QString(""));
        qDebug()<<"user";

    //----------------------------------

    int ccc=0;
      bool ismate;
      ismate=false;
      while (1 ) {
          qDebug()<<"alphabetaEvaluation"<<position1.evaluate2() ;
         // qDebug()<<"ALPHA-BETA-WHO"<<position1.sdPlayer;
           ismate=alpha_beta();
          qDebug()<<"alphabeta_zobristKey"<<position1.zobristKey;
          if(ismate==true ){ qDebug()<<"alpha_beta is loser"; break;}
          // if(ismate==true && win_bug==true){ qDebug()<<"bug random is loser"; break;}
          qDebug()<<"mctsEvaluation"<<position1.evaluate2() ;
        ismate=random2();//mctss();
          if(ismate==true){ qDebug()<<"random is loser"; break;}
         qDebug()<<++ccc;
      }
    show1();
      qDebug()<<"test_ok";



    return a.exec();
}
QDebug operator<<(QDebug out, const std::string& str)
{
 out <<QString::fromStdString(str);
 return out;
}

void show1(){
    QString change="        abcdefg ABCDEFG";
    //QString change="        將士象馬車包卒 帥仕相傌俥炮兵";
    for(int i=3;i<13;i++) qDebug()<<change[position1.squares[i*16+3]]<<change[position1.squares[i*16+4]]<<change[position1.squares[i*16+5]]<<change[position1.squares[i*16+6]]<<change[position1.squares[i*16+7]]<<change[position1.squares[i*16+8]]<<change[position1.squares[i*16+9]]<<change[position1.squares[i*16+10]]<<change[position1.squares[i*16+11]];
}

bool mctss(){
    if(position1.isMate()) return true;

//    qDebug()<<position1.sdPlayer;
    Search search1(&position1);
    unsigned short mvResult;
    mvResult =search1.searchMain();

    while (! position1.legalMove(mvResult)) {show1();mvResult=search1.searchMain();}
    while (! position1.makeMove(mvResult)) {show1();mvResult=search1.searchMain();}

    /*
    position1.legalMove(mvResult);
    qDebug()<<"makeMove"<<position1.makeMove(mvResult);
    if(position1.evaluate2()>=1000){
        qDebug()<<"loster";
        return true;
    }
*/
//    std::stringstream ss;
//    ss<<"MCTS位置"<<(int)(position1.SRC(mvResult)/16)-3<<(position1.SRC(mvResult)%16)-3<<(int)(position1.DST(mvResult)/16)-3<<(position1.DST(mvResult)%16)-3;
//    std::string s;
//    ss>>s;
//    ui->textEdit->setText(ui->textEdit->toPlainText()+  QString::fromStdString(s)+QString("\n") );
    qDebug()<<"MCTS位置"<<(int)(position1.SRC(mvResult)/16)-3<<(position1.SRC(mvResult)%16)-3<<(int)(position1.DST(mvResult)/16)-3<<(position1.DST(mvResult)%16)-3;
    return false;

}
bool alpha_beta(){
    if(position1.isMate()) return true;
    Search search2(&position1);
    unsigned short mvResult=search2.searchMainsecond();

    while (! position1.legalMove(mvResult)) {show1();mvResult=search2.searchMainsecond();}
    while (! position1.makeMove(mvResult)) {show1();mvResult=search2.searchMainsecond();}
   /*
        if (!position1.legalMove(mvResult)) return true;
        if (!position1.makeMove(mvResult)) return true;
  */
       // mvResult=search2->searchMainsecond();

   // while (! position1.makeMove(mvResult)) mvResult=search2->searchMainsecond();

    //position1.legalMove(mvResult);
   // qDebug()<<"makeMove"<<position1.makeMove(mvResult);
//    std::stringstream ss;
//    ss<<"ALPHA-BETA位置"<<(int)(position1.SRC(mvResult)/16)-3<<(position1.SRC(mvResult)%16)-3<<(int)(position1.DST(mvResult)/16)-3<<(position1.DST(mvResult)%16)-3;
//    std::string s;
//    ss>>s;
//    ui->textEdit->setText(ui->textEdit->toPlainText()+  QString::fromStdString(s)+QString("\n") );
    qDebug()<<"ALPHA-BETA位置"<<(int)(position1.SRC(mvResult)/16)-3<<(position1.SRC(mvResult)%16)-3<<(int)(position1.DST(mvResult)/16)-3<<(position1.DST(mvResult)%16)-3;
    show1();

    return false;

}
bool random2(){
    if(position1.isMate()) return true;
    unsigned short mvResult;
         QVector<unsigned short> v=position1.generateMoves();
         QSet< unsigned short> set;
         auto t=v.begin();
          while( t!=v.end()){
           set.insert(*t);
           ++t;
          }
          mcts a(&position1);
         Treenode root(2333,set,nullptr,&a.AllTreeVectorForDestructor);
         mvResult=root.random_set_element(set) ;
         /*
         if(position1.legalMove(mvResult)){
            while (! position1.makeMove(mvResult)) mvResult=root.random_set_element(set) ;
         }else  return true;
         */
         /*
         if(position1.legalMove(mvResult)){
         }else  return true;*/
          while (! position1.legalMove(mvResult)) mvResult=root.random_set_element(set) ;
          while (! position1.makeMove(mvResult)) mvResult=root.random_set_element(set) ;

//         position1.legalMove(mvResult);
//         position1.makeMove(mvResult);
//         std::stringstream ss;
//         ss<<"RANDOM位置"<<(int)(position1.SRC(mvResult)/16)-3<<(position1.SRC(mvResult)%16)-3<<(int)(position1.DST(mvResult)/16)-3<<(position1.DST(mvResult)%16)-3;
//         std::string s;
//         ss>>s;
//         ui->textEdit->setText(ui->textEdit->toPlainText()+QString::fromStdString(s)+QString("\n") );
         qDebug()<<"RANDOM位置"<<(int)(position1.SRC(mvResult)/16)-3<<(position1.SRC(mvResult)%16)-3<<(int)(position1.DST(mvResult)/16)-3<<(position1.DST(mvResult)%16)-3;
        show1();
        return false;
}

bool user1(){


}

