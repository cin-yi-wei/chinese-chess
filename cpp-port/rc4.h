#ifndef RC4_H
#define RC4_H


class rc4
{


public:
    rc4( unsigned char *key );

    void swap ( int , int);

    int nextByte();

    long nextLong ();


private:

    unsigned char  state [256]; // 对称加密中的置换盒 S盒
    int x;
    int y;


};

#endif // RC4_H
