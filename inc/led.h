#ifndef _LED_H
#define _LED_H

#include <stdint.h>

// Based on RH02 board observation:
// PB1 = TX LED (blinks first currently)
// PB0 = RX LED (blinks second currently)

// TX LED - PB1
#define LED_TX_Pin GPIO_PIN_1
#define LED_TX_Port GPIOB
#define LED_TX LED_TX_Port, LED_TX_Pin

// RX LED - PB0
#define LED_RX_Pin GPIO_PIN_0
#define LED_RX_Port GPIOB
#define LED_RX LED_RX_Port, LED_RX_Pin


#define LED_DURATION 25 

void led_init(void);
void led_tx_on(void);
void led_tx_off(void);
void led_tx_blink(uint8_t numblinks);
void led_rx_on(void);
void led_rx_off(void);
void led_rx_blink(uint8_t numblinks);
void led_process(void);

#endif
