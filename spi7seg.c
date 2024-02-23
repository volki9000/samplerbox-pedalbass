// CLK=GPIO09
// SDI=GPIO10
// LCK=GPIO11

/*

rawMCP3XXX.c
Public Domain
2016-03-20

gcc -Wall -pthread -o rawMCP3XXX rawMCP3XXX.c -lpigpio

This code shows how to bit bang SPI using DMA.

Using DMA to bit bang allows for two advantages

1) the time of the SPI transaction can be guaranteed to within a
   microsecond or so.

2) multiple devices of the same type can be read or written
  simultaneously.

This code shows how to read more than one MCP3XXX at a time.

Each MCP3XXX shares the SPI clock, MOSI, and slave select lines but has
a unique MISO line.

This example shows how to read two 12-bit MCP3202 at the same time
as three 10-bit MCP3008.  It only works because the commands for
the two chips are very similar.
*/

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#include <pigpiod_if2.h>

#define CLK 9
#define MOSI 10
//#define CS 11

int main(int argc, char *argv[])
{
   int pi = pigpio_start(NULL, NULL);

   set_mode(pi, CLK, PI_OUTPUT);
   set_mode(pi, MOSI, PI_OUTPUT);
//   set_mode(pi, 11, PI_OUTPUT);
   set_pull_up_down(pi, CLK, PI_PUD_OFF);
   set_pull_up_down(pi, MOSI, PI_PUD_OFF);
//   set_pull_up_down(pi, 11, PI_PUD_OFF);

   unsigned i = 0;
   while (1)
   {
      gpio_write(pi, MOSI, 53 & (1 << (i%8)));
//      gpio_write(pi, CS, i%8 != 0);
      gpio_write(pi, CLK, 1);
      usleep(50);
      gpio_write(pi, CLK, 0);
      usleep(50);
      i++;
   }

   pigpio_stop(pi);
   return 0;
}

