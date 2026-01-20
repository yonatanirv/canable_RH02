#ifndef _CAN_H
#define _CAN_H

enum can_bitrate {
    CAN_BITRATE_10K = 0,
    CAN_BITRATE_20K,
    CAN_BITRATE_50K,
    CAN_BITRATE_100K,
    CAN_BITRATE_125K,
    CAN_BITRATE_250K,
    CAN_BITRATE_500K,
    CAN_BITRATE_750K,
    CAN_BITRATE_1000K,

	CAN_BITRATE_INVALID,
};

typedef enum can_bus_state {
    OFF_BUS = 0,
    ON_BUS = 1,
} can_bus_state_t;


// CAN transmit buffering
#define TXQUEUE_LEN 28 // Number of buffers allocated
#define TXQUEUE_DATALEN 8 // CAN DLC length of data buffers

typedef struct cantxbuf_
{
	uint8_t data[TXQUEUE_LEN][TXQUEUE_DATALEN]; // Data buffer
	CAN_TxHeaderTypeDef header[TXQUEUE_LEN]; // Header buffer
	uint8_t head; // Head pointer
	uint8_t tail; // Tail pointer
	uint8_t full; // TODO: Set this when we are full, clear when the tail moves one.
} can_txbuf_t;


// CAN Error Status structure
typedef struct can_status_
{
    uint8_t bus_state;      // 0=off, 1=on
    uint8_t error_warning;  // Error warning flag (TEC or REC >= 96)
    uint8_t error_passive;  // Error passive flag (TEC or REC >= 128)
    uint8_t bus_off;        // Bus-off flag (TEC >= 256)
    uint8_t last_error;     // Last error code: 0=none, 1=stuff, 2=form, 3=ack, 4=bit_rec, 5=bit_dom, 6=crc
    uint8_t tx_err_cnt;     // Transmit error counter
    uint8_t rx_err_cnt;     // Receive error counter
} can_status_t;

// Last Error Code values
#define CAN_LEC_NONE      0  // No error
#define CAN_LEC_STUFF     1  // Stuff error
#define CAN_LEC_FORM      2  // Form error
#define CAN_LEC_ACK       3  // Acknowledgment error (no ACK received)
#define CAN_LEC_BIT_REC   4  // Bit recessive error
#define CAN_LEC_BIT_DOM   5  // Bit dominant error
#define CAN_LEC_CRC       6  // CRC error


// Prototypes
void can_init(void);
void can_enable(void);
void can_disable(void);
void can_set_bitrate(enum can_bitrate bitrate);
void can_set_silent(uint8_t silent);
void can_set_autoretransmit(uint8_t autoretransmit);
uint32_t can_tx(CAN_TxHeaderTypeDef *tx_msg_header, uint8_t *tx_msg_data);
uint32_t can_rx(CAN_RxHeaderTypeDef *rx_msg_header, uint8_t *rx_msg_data);
void can_get_status(can_status_t *status);


void can_process(void);

uint8_t is_can_msg_pending(uint8_t fifo);
CAN_HandleTypeDef* can_gethandle(void);

#endif // _CAN_H
