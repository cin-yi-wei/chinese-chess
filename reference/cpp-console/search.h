#ifndef SEARCH_H
#define SEARCH_H
#include "position.h"
class Position;
class Search
{
public:
    Position *pos;
    Search(Position *);
    ~Search();

    unsigned short mvResult;



    unsigned short searchMain();
    unsigned short searchMainsecond();
    void maxMinSearch();
    short alphaBetaSearch(short , short, int);
    short minSearch(unsigned char depth);
    short maxSearch(unsigned char);

private:
 static const unsigned char MINMAXDEPTH=4;
 //static const short MATE_VALUE = 10000;
};
//unsigned char MINMAXDEPTH=1;
#endif // SEARCH_H
