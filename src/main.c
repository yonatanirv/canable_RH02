//
// CANable firmware
//

#include "stm32f0xx.h"
#include "stm32f0xx_hal.h"

#include "usb_device.h"
#include "usbd_cdc_if.h"
#include "can.h"
#include "slcan.h"
#include "system.h"
#include "led.h"
#include "error.h"


int main(void)
{
    // Initialize peripherals
    system_init();
    can_init();
    led_init();
    usb_init();

    // Boot LED sequence: RX 3x, then TX 3x
    led_rx_blink(3);   // RX first
    HAL_Delay(200);
    led_tx_blink(3);   // TX second
    
    // Turn both LEDs off after boot sequence
    led_rx_off();
    led_tx_off();

    // Storage for status and received message buffer
    CAN_RxHeaderTypeDef rx_msg_header;
    uint8_t rx_msg_data[8] = {0};
    uint8_t msg_buf[SLCAN_MTU];


    while(1)
    {
        cdc_process();
        led_process();
        can_process();

        // If CAN message receive is pending, process the message
        if(is_can_msg_pending(CAN_RX_FIFO0))
        {
			// If message received from bus, parse the frame
			if (can_rx(&rx_msg_header, rx_msg_data) == HAL_OK)
			{
				uint16_t msg_len = slcan_parse_frame((uint8_t *)&msg_buf, &rx_msg_header, rx_msg_data);

				// Transmit message via USB-CDC
				if(msg_len)
				{
					uint8_t result = CDC_Transmit_FS(msg_buf, msg_len);
					if(result != 0) // USBD_OK = 0
					{
						// USB busy - blink TX LED to show dropped frame
						led_tx_on();
					}
				}
			}
        }
    }
}

