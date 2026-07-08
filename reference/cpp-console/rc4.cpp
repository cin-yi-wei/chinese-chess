#include "rc4.h"
#include <string.h>
#include <QDebug>
rc4::rc4(unsigned char *key)
{
    this->x=0;
    this->y=0;
    for (int i = 0; i < 256; i ++) {
      this->state[i]=i;
    }
    unsigned char j = 0;
    for (int i = 0; i < 256; i ++) {
      j = (j + this->state[i] + key[i % strlen((char*)key) ]) & 0xff;
      this->swap(i, j);
    }
}

void rc4::swap(int i ,int j){
    unsigned char temp=this->state[i];
    this->state[i]=this->state[j];
    this->state[j]=temp;
}

int rc4::nextByte(){
  this->x = (this->x + 1) & 0xff;
  this->y = (this->y + this->state[this->x]) & 0xff;
  this->swap(this->x, this->y);
  int t = (this->state[this->x] + this->state[this->y]) & 0xff;
  return this->state[t];
}

// 生成32位随机数
long rc4::nextLong(){
  int n0 = this->nextByte();
  int n1 = this->nextByte();
  int n2 = this->nextByte();
  int n3 = this->nextByte();
  return n0 + (n1 << 8) + (n2 << 16) + ((n3 << 24) & 0xffffffff);
}
