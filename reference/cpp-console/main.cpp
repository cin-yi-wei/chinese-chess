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
#include <QFile>
#include <QProcess>
#include <QtCore/qmath.h>
#include <float.h>
bool alpha_beta();
bool mctss();
bool random2();
bool user1();
bool init();
void show1();
QString file1();
unsigned char pos_map_1(int );
int pos_map_2(unsigned char );
Position position1;
static float x_minn,x_maxx,y_minn,y_maxx;
static QVector<float> x_total,y_total,x_total_pre,y_total_pre;
static float image_true_pos_x[9],image_true_pos_y[4];
static int times=0,timess=0;
static bool bool_matrix_pre[36],bool_matrix[36];
static int eat=45;
int main(int argc, char *argv[])
{
    QCoreApplication a(argc, argv);
/*
    QProcess p;
    QStringList params;
    params << "arms.py"<< (QString)"1" << (QString)"2"; //dst eat
    p.start("python3", params);
    p.waitForFinished(-1);
    params.clear();
*/
    //---------------------init
    //    position1.fromFen("1nbakabn1/9/1c5c1/p1p1p1p1p/9/9/9/9/4K3r/8r w - - 0 1");
        //position1.fromFen("rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1");
        // position1.fromFen("2bakab2/9/4c1n2/p3p1p1p/P1p6/5nP2/3r4P/4B3R/4r4/1cBA1K1NR w - - 0 1");
        //position1.fromFen("4k4/1c5c1/9/1c5c1/9/r6c1/6P2/4BA3/1R1K5/8n w - - 0 1");
        position1.fromFen("4k4/9/9/9/9/9/n7c/4n4/2R3r2/C3KA2r w - - 0 1");
        position1.chkList.push(position1.checked());
        qDebug()<< position1.evaluate() << position1.sdPlayer;
    //    position1.legalMove(position1.MOVE(183,167));
    //    position1.makeMove(position1.MOVE(183,167));
        /*
        position1.legalMove(position1.MOVE(153,137));
        position1.makeMove(position1.MOVE(153,137));
        */
        qDebug()<< position1.evaluate2() << position1.sdPlayer;
       // ui->textEdit->setText(QString(""));
        qDebug()<<"user";

    //----------------------------------
     init();

      bool ismate;
      ismate=false;
      while (1 ) {

          // if(ismate==true && win_bug==true){ qDebug()<<"bug random is loser"; break;}
          qDebug()<<"alpha_beta_Evaluation"<<position1.evaluate2() ;
        ismate=alpha_beta();//mctss();
          if(ismate==true){ qDebug()<<"alpha_beta is loser"; break;}


          qDebug()<<"user_Evaluation"<<position1.evaluate2() ;
         // qDebug()<<"ALPHA-BETA-WHO"<<position1.sdPlayer;
           ismate=user1();
          qDebug()<<"user_zobristKey"<<position1.zobristKey;
          if(ismate==true ){ qDebug()<<"user is loser"; break;}


         qDebug()<<++times;
      }
    show1();

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

/*
    //SRC DST
    bool_matrix_pre[pos_map_2(position1.SRC(mvResult))]=false;
    bool_matrix_pre[pos_map_2(position1.DST(mvResult))]=true;
*/

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
    qDebug()<<QString::number(pos_map_2(position1.SRC(mvResult)))<<QString::number(pos_map_2(position1.DST(mvResult)));
    show1();
    QProcess p;
    QStringList params;
    position1.undoMakeMove();
    if(position1.squares[position1.DST(mvResult)]!=0 ){ // eat

        qDebug()<<"innnnnnnnnnnnnnnnnnnnntooooooooooooooooooo";
        params << "delay_control.py"<< QString::number(pos_map_2(position1.DST(mvResult))) << QString::number(eat) ; //dst eat
        p.start("python3", params);
        p.waitForFinished(-1);
        params.clear();
        eat--;

        qDebug()<<"innnnnnnnnnnnnnnnnnnnntooooooooooooooooooo";
    }
    position1.makeMove(mvResult);
    //move
        params << "delay_control.py"<<QString::number(pos_map_2(position1.SRC(mvResult)))<<QString::number(pos_map_2(position1.DST(mvResult)));//src dst
        p.start("python3", params);
        p.waitForFinished(-1);
        params.clear();



    params << "change.py"; // -arg1 arg1;
    p.start("python", params);
    p.waitForFinished(-1);
    params.clear();

    params << "change2.py"; // -arg1 arg1;
    p.start("python", params);
    p.waitForFinished(-1);
    params.clear();
    QString aaa=file1();
    while (aaa!="0") {
        aaa=file1();
    }
    QFile inputFile(QString("/home/isslab/darknet/result.txt"));
    inputFile.open(QIODevice::ReadOnly);
    if (!inputFile.isOpen()) return false;
    QTextStream stream(&inputFile);
    int i=0;
    QString x_min,y_min,x_max,y_max;
    float x_center,y_center;

    while (!stream.atEnd())
    {
         QString result = stream.readLine();
         if(i%5==1) {x_min=result; }
         if(i%5==2) {y_min=result; }
         if(i%5==3) {x_max=result; }
         if(i%5==4) {y_max=result;
                     x_center=((x_max.toFloat()-x_min.toFloat())/2)+x_min.toFloat();
                     y_center=((y_max.toFloat()-y_min.toFloat())/2)+y_min.toFloat();
                     x_total.push_back(x_center); y_total.push_back(y_center);
                    }
         i++;
    }
    inputFile.close();
    for(int i=0;i<36;i++) bool_matrix[i]=false;
   for(int k=0;k<x_total.size();k++){
        for(int i=0;i<9;i++){
            for(int j=0;j<4;j++){ //i*4+j
              if(qSqrt(qPow(x_total[k]-image_true_pos_x[i],2) +qPow(y_total[k]-image_true_pos_y[j],2))< (x_maxx-x_minn)/16) bool_matrix[i*4 +j]= true;
                //qDebug()<<k<<i<<j <<qSqrt(qPow(x_total[k]-image_true_pos_x[i],2) +qPow(y_total[k]-image_true_pos_y[j],2)) ;
            }
        }
    }
   unsigned char source=0,end=0;
   int b=0;
   QVector<float> onlyone;
   QVector<int> index_a;
   for(int i=0;i<36;i++) {
       if((bool_matrix[i] ^bool_matrix_pre[i])==true ){
           b++;
           if(bool_matrix[i]==false) source=pos_map_1(i);
           if(bool_matrix[i]==true) end=pos_map_1(i);
       }
   }

   if(b==1){
        for(int i=0;i<x_total.size();i++){
            float min=FLT_MAX;
            long index_1=0;
            for(int j=0;j<x_total_pre.size();j++){
              float a=qSqrt(qPow((x_total[i]- x_total_pre[j]),2)+qPow((y_total[i]- y_total_pre[j]),2));
              if(min>a) {min =a; index_1=i;}
            }
            onlyone.push_back(min);
            index_a.push_back(index_1);
        }
        long index= std::max_element(onlyone.begin(),onlyone.end()) - onlyone.begin();
        for(int i=0;i<9;i++){
            for(int j=0;j<4;j++){ //i*4+j
              if(qSqrt(qPow(x_total[index_a[index]]-image_true_pos_x[i],2) +qPow(y_total[index_a[index]]-image_true_pos_y[j],2))< (x_maxx-x_minn)/16) end=pos_map_1(i*4+j);
            }
        }
   }

  for(int i=0;i<36;i++) qDebug() << bool_matrix[i] ;
  qDebug()<<"source"<<source<<"end"<<end<<"b"<<b;


  for(int i=0;i<36;i++) bool_matrix_pre[i] =bool_matrix[i];
  x_total_pre=x_total;y_total_pre=y_total;
  x_total.clear(); y_total.clear();

  params << "change.py"; // -arg1 arg1;
  p.start("python", params);
  p.waitForFinished(-1);
  params.clear();

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

unsigned char pos_map_1(int a){
 if(a==0 ) return (unsigned char )203 ;
  if(a==1 ) return (unsigned char )187 ;
 if(a==2 ) return  (unsigned char )171;
  if(a==3 ) return  (unsigned char )155;
   if(a==4 ) return (unsigned char )202 ;
    if(a==5 ) return  (unsigned char )186;
     if(a==6 ) return  (unsigned char )170;
     if(a== 7) return  (unsigned char )154;
      if(a==8 ) return (unsigned char )201 ;
     if(a== 9) return  (unsigned char )185;
      if(a==10 ) return  (unsigned char )169;
       if(a==11 ) return  (unsigned char )153;
        if(a==12 ) return (unsigned char )200 ;
         if(a==13 ) return  (unsigned char )184;
         if(a== 14) return  (unsigned char )168;
          if(a==15 ) return  (unsigned char )152;
         if(a== 16) return  (unsigned char )199;
          if(a==17 ) return  (unsigned char )183;
           if(a==18 ) return  (unsigned char )167;
            if(a==19 ) return  (unsigned char )151;
             if(a==20 ) return  (unsigned char )198;
             if(a==21 ) return  (unsigned char )182;
              if(a==22 ) return  (unsigned char )166;
             if(a== 23) return  (unsigned char )150;
              if(a==24 ) return  (unsigned char )197;
               if(a==25 ) return  (unsigned char )181;
                if(a==26 ) return  (unsigned char )165;
                 if(a==27 ) return  (unsigned char )149;
                 if(a== 28) return  (unsigned char )196;
                  if(a== 29) return  (unsigned char )180;
                 if(a== 30) return  (unsigned char )164;
                  if(a==31 ) return  (unsigned char )148;
                   if(a==32 ) return  (unsigned char )195;
                    if(a==33 ) return  (unsigned char )179;
                     if(a==34 ) return  (unsigned char )163;
                      if(a==35 ) return  (unsigned char )147;
}
int pos_map_2(unsigned char a){
 if(a==203 ) return (int) 0;
  if(a==187 ) return (int ) 1;
 if(a==171 ) return  (int )2;
  if(a==155 ) return  (int )3;
   if(a==202 ) return (int ) 4;
    if(a==186 ) return  (int)5;
     if(a==170 ) return  (int )6;
     if(a== 154) return  (int )7;
      if(a==201 ) return (int ) 8;
     if(a== 185) return  (int )9;
      if(a==169 ) return  (int )10;
       if(a==153 ) return  (int )11;
        if(a==200 ) return (int ) 12;
         if(a==184 ) return  (int)13;
         if(a== 168) return  (int)14;
          if(a==152 ) return  (int )15;
         if(a== 199) return  (int )16;
          if(a==183 ) return  (int)17;
           if(a==167 ) return  (int)18;
            if(a==151 ) return  (int)19;
             if(a==198 ) return  (int )20;
             if(a==182 ) return  (int)21;
              if(a==166 ) return  (int)22;
             if(a== 150) return  (int)23;
              if(a==197 ) return  (int)24;
               if(a==181 ) return  (int)25;
                if(a==165 ) return  (int)26;
                 if(a==149 ) return  (int)27;
                 if(a== 196) return  (int)28;
                  if(a== 180) return  (int)29;
                 if(a== 164) return  (int)30;
                  if(a==148 ) return  (int)31;
                   if(a==195 ) return  (int)32;
                    if(a==179 ) return  (int)33;
                     if(a==163 ) return  (int)34;
                      if(a==147 ) return  (int)35;
}

QString file1(){
    QFile inputFile(QString("/var/www/html/who"));
    inputFile.open(QIODevice::ReadOnly);
    if (!inputFile.isOpen()) return 0;
    QTextStream stream(&inputFile);
    QString line = stream.readLine();
    inputFile.close();
    return  line;
}

bool init(){
    QString aaa=file1();
    while (aaa!="0") {
        aaa=file1();
    }
    QFile inputFile(QString("/home/isslab/darknet/result.txt"));
    inputFile.open(QIODevice::ReadOnly);
    if (!inputFile.isOpen()) return false;
    QTextStream stream(&inputFile);
    int i=0;
    QString x_min,y_min,x_max,y_max;
    float x_center,y_center;
    while (!stream.atEnd())
    {
         QString result = stream.readLine();
         if(i%5==1) {x_min=result; }
         if(i%5==2) {y_min=result; }
         if(i%5==3) {x_max=result; }
         if(i%5==4) {y_max=result;
                     x_center=((x_max.toFloat()-x_min.toFloat())/2)+x_min.toFloat();
                     y_center=((y_max.toFloat()-y_min.toFloat())/2)+y_min.toFloat();
                     x_total_pre.push_back(x_center); y_total_pre.push_back(y_center);
                    }
         i++;
    }
    inputFile.close();
        x_minn= *std::min_element(x_total_pre.constBegin(), x_total_pre.constEnd());
        x_maxx= *std::max_element(x_total_pre.constBegin(), x_total_pre.constEnd());
        y_minn= *std::min_element(y_total_pre.constBegin(), y_total_pre.constEnd());
        y_maxx= *std::max_element(y_total_pre.constBegin(), y_total_pre.constEnd());
        for(int i=0;i<9;i++) image_true_pos_x[i]= ((x_maxx-x_minn)/8)*i +x_minn;
        for(int i=0;i<4;i++) image_true_pos_y[i]= ((y_maxx-y_minn)/3)*i +y_minn;
        for(int i=0;i<36;i++) bool_matrix_pre[i]=false;
        bool_matrix_pre[0]=true;bool_matrix_pre[3]=true;bool_matrix_pre[12]=true;bool_matrix_pre[16]=true; bool_matrix_pre[9]=true;
        bool_matrix_pre[18]=true;bool_matrix_pre[25]=true;bool_matrix_pre[32]=true;bool_matrix_pre[35]=true; //init board
        QProcess p;
        QStringList params;
        params << "change.py"; // -arg1 arg1;
        p.start("python", params);
        p.waitForFinished(-1);
        qDebug()<<"init";
}

bool user1(){
  if(position1.isMate()) return true;
  QString aaa=file1();
  while (aaa!="0") {
      aaa=file1();
  }
  QFile inputFile(QString("/home/isslab/darknet/result.txt"));
  inputFile.open(QIODevice::ReadOnly);
  if (!inputFile.isOpen()) return false;
  QTextStream stream(&inputFile);
  int i=0;
  QString x_min,y_min,x_max,y_max;
  float x_center,y_center;

  while (!stream.atEnd())
  {
       QString result = stream.readLine();
       if(i%5==1) {x_min=result; }
       if(i%5==2) {y_min=result; }
       if(i%5==3) {x_max=result; }
       if(i%5==4) {y_max=result;
                   x_center=((x_max.toFloat()-x_min.toFloat())/2)+x_min.toFloat();
                   y_center=((y_max.toFloat()-y_min.toFloat())/2)+y_min.toFloat();
                   x_total.push_back(x_center); y_total.push_back(y_center);
                  }
       i++;
  }
  inputFile.close();
  for(int i=0;i<36;i++) bool_matrix[i]=false;
 for(int k=0;k<x_total.size();k++){
      for(int i=0;i<9;i++){
          for(int j=0;j<4;j++){ //i*4+j
            if(qSqrt(qPow(x_total[k]-image_true_pos_x[i],2) +qPow(y_total[k]-image_true_pos_y[j],2))< (x_maxx-x_minn)/16) bool_matrix[i*4 +j]= true;
              //qDebug()<<k<<i<<j <<qSqrt(qPow(x_total[k]-image_true_pos_x[i],2) +qPow(y_total[k]-image_true_pos_y[j],2)) ;
          }
      }
  }
 unsigned char source=0,end=0;
 int b=0;
 QVector<float> onlyone;
 QVector<int> index_a;
 for(int i=0;i<36;i++) {
     if((bool_matrix[i] ^bool_matrix_pre[i])==true ){
         b++;
         if(bool_matrix[i]==false) source=pos_map_1(i);
         if(bool_matrix[i]==true) end=pos_map_1(i);
     }
 }

 if(b==1){
      for(int i=0;i<x_total.size();i++){
          float min=FLT_MAX;
          long index_1=0;
          for(int j=0;j<x_total_pre.size();j++){
            float a=qSqrt(qPow((x_total[i]- x_total_pre[j]),2)+qPow((y_total[i]- y_total_pre[j]),2));
            if(min>a) {min =a; index_1=i;}
          }
          onlyone.push_back(min);
          index_a.push_back(index_1);
      }
      long index= std::max_element(onlyone.begin(),onlyone.end()) - onlyone.begin();
      for(int i=0;i<9;i++){
          for(int j=0;j<4;j++){ //i*4+j
            if(qSqrt(qPow(x_total[index_a[index]]-image_true_pos_x[i],2) +qPow(y_total[index_a[index]]-image_true_pos_y[j],2))< (x_maxx-x_minn)/16) end=pos_map_1(i*4+j);
          }
      }
 }

for(int i=0;i<36;i++) qDebug() << bool_matrix[i] ;
qDebug()<<"source"<<source<<"end"<<end<<"b"<<b;


qDebug()<<position1.legalMove(position1.MOVE(source,end));
position1.makeMove2(position1.MOVE(source,end));
show1();
for(int i=0;i<36;i++) bool_matrix_pre[i] =bool_matrix[i];
x_total_pre=x_total;y_total_pre=y_total;
x_total.clear(); y_total.clear();

return  false;
 //return random2();
}


