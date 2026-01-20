//
// LED: Handles blinking of status light
//

#include "stm32f0xx_hal.h"
#include "led.h"


// Private variables
static uint32_t led_tx_laston = 0;
static uint32_t led_rx_laston = 0;
static uint32_t led_tx_lastoff = 0;
static uint32_t led_rx_lastoff = 0;


// Initialize LED GPIOs
void led_init(void)
{
    __HAL_RCC_GPIOB_CLK_ENABLE();
    
    GPIO_InitTypeDef GPIO_InitStruct;
    
    // Initialize both LEDs on GPIOB (PB0 = RX, PB1 = TX)
    GPIO_InitStruct.Pin = LED_TX_Pin | LED_RX_Pin;
    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

    // Turn both LEDs off initially
    led_tx_off();
    led_rx_off();
}


// Turn TX LED on
void led_tx_on(void)
{
    // Make sure the LED has been off for at least LED_DURATION before turning on again
    // This prevents a solid status LED on a busy canbus
    if(led_tx_laston == 0 && HAL_GetTick() - led_tx_lastoff > LED_DURATION)
    {
        HAL_GPIO_WritePin(LED_TX, 0);  // ON (active low)
        led_tx_laston = HAL_GetTick();
    }
}


// Turn TX LED off
void led_tx_off(void)
{
    HAL_GPIO_WritePin(LED_TX, 1);  // OFF (active low)
    led_tx_laston = 0;
}


// Blink TX LED (blocking)
void led_tx_blink(uint8_t numblinks)
{
    for(uint8_t i = 0; i < numblinks; i++)
    {
        HAL_GPIO_WritePin(LED_TX, 0);  // ON
        HAL_Delay(100);
        HAL_GPIO_WritePin(LED_TX, 1);  // OFF
        HAL_Delay(100);
    }
}


// Turn RX LED on
void led_rx_on(void)
{
    // Make sure the LED has been off for at least LED_DURATION before turning on again
    // This prevents a solid status LED on a busy canbus
    if(led_rx_laston == 0 && HAL_GetTick() - led_rx_lastoff > LED_DURATION)
    {
        HAL_GPIO_WritePin(LED_RX, 0);  // ON (active low)
        led_rx_laston = HAL_GetTick();
    }
}


// Turn RX LED off
void led_rx_off(void)
{
    HAL_GPIO_WritePin(LED_RX, 1);  // OFF (active low)
    led_rx_laston = 0;
}


// Blink RX LED (blocking)
void led_rx_blink(uint8_t numblinks)
{
    for(uint8_t i = 0; i < numblinks; i++)
    {
        HAL_GPIO_WritePin(LED_RX, 0);  // ON
        HAL_Delay(100);
        HAL_GPIO_WritePin(LED_RX, 1);  // OFF
        HAL_Delay(100);
    }
}


// Process time-based LED events
void led_process(void)
{
    // If TX LED has been on for long enough, turn it off
    if(led_tx_laston > 0 && HAL_GetTick() - led_tx_laston > LED_DURATION)
    {
        HAL_GPIO_WritePin(LED_TX, 1);  // OFF
        led_tx_laston = 0;
        led_tx_lastoff = HAL_GetTick();
    }

    // If RX LED has been on for long enough, turn it off
    if(led_rx_laston > 0 && HAL_GetTick() - led_rx_laston > LED_DURATION)
    {
        HAL_GPIO_WritePin(LED_RX, 1);  // OFF
        led_rx_laston = 0;
        led_rx_lastoff = HAL_GetTick();
    }
}
