from threading import Event, Thread, Timer
from Queue import Queue, Empty
from serial import Serial
from time import sleep
import logging
import string
import shlex

import smspdu

#Personal data protection technique:
#All the logging statements&prints that can contain private data
#are to be marked with PDATA. If the data is to be sent to developers,
#this would make it easier for the users to clean it if they want to.
#(though it could, of course, make the debugging harder.)

def has_nonascii(s):
    ascii_chars = string.ascii_letters+string.digits+"!@#$%^&*()_+\|{}[]-_=+'\",.<>?:; "
    return any([char for char in ascii_chars if char not in ascii_chars])

def is_csv(s):
    #Is this stupid or KISS? I wrote it, and now I can't tell =(
    return "," in s

class ATError(Exception):
    def __init__(self, expected=None, received=None):
        self.received = received
        self.expected = expected
        message = "Expected {}, got {}".format(expected, repr(received))
        Exception.__init__(self, message)
        self.received = received

class Phone():
    def __init__(self, modem):
        pass

    def get_status(self):
        pass
    
    def send_message(self, recipient, text):
        pass

    def get_caller_id(self):
        pass

    def get_call_duration(self):
        pass

    def signal_call_started(self):
        pass

    def signal_missed_call(self):
        pass

    def signal_message_received(self):
        pass

    def get_new_messages(self):
        pass

    def get_hardware_info(self):
        return modem.get_manufacturer(), modem.get_model(), modem.get_imei()


class Modem():
    #Serial port settings
    read_buffer_size = 1000

    #Some constants
    linesep = '\r\n'
    ok_response = 'OK'
    error_response = 'ERROR'
    clcc_header = "+CLCC:"
    clip_header = "+CLIP:"
    clcc_enabled = False

    #Status storage variables
    status = {"state":"idle",
              "type":None}

    #The last Caller ID that was received from the modem is stored
    #It's cleared once the call ends, and once it's set it looks like this:
    #last_callerid = {"number":"something", "type":"unknown"/"international"/"national"/"network-specific"}
    last_callerid = None

    def __init__(self, serial_path="/dev/ttyAMA0", serial_timeout=0.5, read_timeout=0.2):
        self.serial_path = serial_path
        self.serial_timeout = serial_timeout
        self.read_timeout = read_timeout
        self.executing_command = Event()
        self.should_monitor = Event()
        self.unexpected_queue = Queue()

    def init_modem(self):
        self.port = Serial(self.serial_path, 115200, timeout=self.serial_timeout)
        self.at()
        self.enable_verbosity()
        self.enable_clcc()
        self.enable_clip()
        self.set_message_mode("pdu")
        #self.at_command("AT+CSSN=1,1")
        print("Battery voltage is: {}".format(self.get_voltage()))
        self.save_settings()

    def deinit_modem(self):
        try:
            self.port.close()
        except: #Could be not created or already closed
            pass

   #Functions that the user will be calling

    def call(self, number):
        return self.at_command("ATD{};".format(number))

    def ussd(self, string):
        result = self.at_command('AT+CUSD=1,"{}"'.format(string))

    def hangup(self):
        return self.at_command("ATH", noresponse=True)

    def answer(self):
        return self.at_command("ATA")

    #Debugging helpers

    def pprint_status(self):
        print("--------------------------")
        print("New state: {}".format(self.status["state"]))
        if self.last_callerid:
            print("Caller ID: {}, type: {}".format(self.last_callerid["number"],
                                                   self.last_callerid["type"]))

    #Callbacks that change the call state and clean state variables
    #Not to be overridden directly as they might have desirable side effects
    #Also, they're called in a hackish way and overriding would fail anyway

    #Call-specific callbacks

    #  "0":on_talking,
    def on_talking(self):
        #Call answered, voice comms established
        self.status["state"] = "talking"
        self.pprint_status()

    #  "1":on_held,
    def on_held(self):
        #Held call signal
        if self.status["type"] == "incoming":
            self.status["state"] = "held"
        else:
            self.status["state"] = "holding"
        self.pprint_status()

    #  "2":on_dialing,
    def on_dialing(self):
        assert(self.status["type"] == "outgoing")
        self.status["state"] = "dialing"
        self.pprint_status()

    #  "3":on_alerting,
    def on_alerting(self):
        assert(self.status["type"] == "outgoing")
        self.status["state"] = "alerting"
        self.pprint_status()

    #  "4":on_incoming,
    def on_incoming(self):
        assert(self.status["type"] == "incoming")
        self.status["state"] = "incoming_call"
        self.pprint_status()

    #  "5":on_waiting,
    def on_waiting(self):
        assert(self.status["type"] == "incoming")
        self.status["state"] = "waiting"
        self.pprint_status()

    #  "6":on_disconnect
    def on_disconnect(self, incoming=True):
        #Either finished or missed call
        if self.status["type"] == "incoming" and self.status["state"] not in ["held", "talking"]:
            self.status["state"] = "missed_call"
        else:
            self.status["state"] = "finished"
        Timer(3, self.on_idle).start()
        self.pprint_status()

    def on_idle(self):
        #Cleans up variables and sets state to "idle"
        #Only runs from threading.Timer since modem sends no "idle" CLCC message
        #Safety check to ensure this doesn't run during a call 
        #if call happens right after previous call ends:
        if self.status["state"] not in ["active_call", "held"]:
            self.last_callerid = None
            self.status["state"] = "idle"
            self.pprint_status()

    #SMS callbacks

    def on_incoming_message(self, cmti_line):
        #New message signal
        print("You've got mail! Line: {}".format(cmti_line[len("+CMTI:"):]).strip())
        self.read_all_messages()

    def read_all_messages(self):
        prev_timeout = self.serial_timeout
        self.serial_timeout = 1 #TODO: get message count and base timeout on that
        output = self.at_command("AT+CMGL")
        self.serial_timeout = prev_timeout
        if len(output) % 2 == 1:
            print("CMGL output lines not in pairs?")
            print("PDATA: {}".format(repr(output)))
            return False
        cmgl_header = "+CMGL: "
        for i in range(len(output)/2):
            header = output[i*2]
            if not header.startswith(cmgl_header):
                print("Line presumed to be CMGL doesn't start with CMGL header!")
            id, x, x, pdu_len = header[len(cmgl_header):].split(",")
            smsc_pdu_str = output[(i*2)+1]
            self.decode_message(smsc_pdu_str, pdu_len, id)

    def decode_message(self, smsc_pdu_str, pdu_len, id):
        print("Reading message {}".format(id))
        pdu_len = int(pdu_len) #Just in case
        smsc_len = len(smsc_pdu_str) - pdu_len*2 #We get PDU length in octets
        if smsc_len == 0:
            print("No SMSC in PDU - seems like it can happen!")
        pdu_str = smsc_pdu_str[smsc_len:] #Discarding SMSC info
        #SMSC info might actually be useful in the future - maybe its spoofing could be detected? Does it even happen?
        smspdu.pdu.dump(pdu_str)

    #Non-CLCC exclusive callbacks
    #(the non-CLCC path might not even work that well, for what I know)
    def on_ring(self):
        print("Ring ring ring bananaphone!")

    #AT command-controlled modem settings and simple functions

    def get_manufacturer(self):
        return self.at_command("AT+CGMI")

    def get_model(self):
        return self.at_command("AT+CGMM")

    def get_imei(self):
        return self.at_command("AT+GSN")

    def save_settings(self):
        self.at_command("AT&W")

    def enable_verbosity(self):
        return self.at_command('AT+CMEE=1')

    def enable_clcc(self):
        self.clcc_enabled = True
        return self.at_command('AT+CLCC=1')

    def set_message_mode(self, mode_str):
        if mode_str.lower() == "text":
            return self.at_command('AT+CMGF=1')
        elif mode_str.lower() == "pdu":
            return self.at_command('AT+CMGF=0')
        else:
            raise ValueError("Wrong message mode: {}".format(mode_str))

    def enable_clip(self):
        return self.at_command('AT+CLIP=1')

    def at(self):
        response = self.at_command('AT')
        if response is True: return
        raise ATError(expected=self.ok_response, received=response)

    #Auxiliary functions that aren't related to phone functionality
    #TODO: Expose this to an external API of sorts

    def get_voltage(self):
        answer = self.at_command('AT+CBC')
        if not answer.startswith('+CBC'): return 0.0 #TODO - this needs to be better!
        voltage_str = answer.split(':')[1].split(',')[2]
        voltage = round(int(voltage_str)/1000.0, 2)
        return voltage

    #Call status and Caller ID message processing code
    #This is where we get call information info

    def process_clcc(self, clcc_line):
        clcc_line = clcc_line[len(self.clcc_header):]
        clcc_line = clcc_line.strip()
        elements = clcc_line.split(',')
        if len(elements) < 5:
            print("Unrecognized number of CLCC elements!")
            print("PDATA: "+repr(elements))
            return
        elif len(elements) > 8:
            print("Too much CLCC elements!")
            print("PDATA: "+repr(elements))
            elements = elements[:8]
        if len(elements) > 7: #Elements 5 and 6 are present
            self.set_callerid(elements[5], elements[6])
        call_type = elements[1]
        call_status = elements[2]
        self.status["type"] = "incoming" if call_type=="1" else "outgoing" 
        self.clcc_mapping[call_status](self)

    def process_clip(self, line):
        clip_line = line[len(self.clip_header):]
        clip_line = clip_line.strip()
        elements = clip_line.split(',')
        if len(elements) < 2:
            raise ATError(expected="valid CLIP string with >2 elements", received=line)
        elif len(elements) < 6:
            print("Less than 6 CLIP elements, noting")
            print("PDATA: "+repr(elements))
        elif len(elements) > 6:
            print("Too much CLIP elements, what's wrong?!")
            print("PDATA: "+repr(elements))
            elements = elements[:6]
        number = elements[0]
        type_id = elements[1]
        self.set_callerid(number, type_id)

    def set_callerid(self, number, type_id):
        clip_type_mapping = {"129":"unknown",
                             "161":"national",
                             "145":"international",
                             "177":"network-specific"}
        if type_id not in clip_type_mapping.keys():
            print("PDATA: CLIP type id {} not found in type mapping!".format(type_id))
            type = "unknown"
        else:
            type = clip_type_mapping[type_id]
        #Setting status variable
        self.last_callerid = {"number":number.strip('\"'), "type":type}
        
    clcc_mapping = { 
      "0":on_talking,
      "1":on_held,
      "2":on_dialing,
      "3":on_alerting,
      "4":on_incoming,
      "5":on_waiting,
      "6":on_disconnect
    }

    def on_clcc(self, clcc_line):
        for i in range(4):
            if not has_nonascii(clcc_line) or not is_csv(clcc_line): 
                break
            print("Garbled call info line! Try {}, line: {}".format(i, clcc_line))
            sleep(1)
            clcc_response = self.at_command("AT+CLCC", nook=True)
            print(repr(lines))
            for line in lines:
                if line.startswith(self.clcc_header):
                    clcc_line = line
                else:
                    self.queue_unexpected_data(line)
        if has_nonascii(clcc_line) or not is_csv(clcc_line):
            print("Still garbled CLCC line!"); return
        #print("Call info OK, line: {}".format(repr(clcc_line[len(self.clcc_header):])).strip())
        self.process_clcc(clcc_line)

    def on_clip(self, line):
        self.process_clip(line)

    #Low-level functions

    def check_input(self):
        input = self.port.read(self.read_buffer_size)
        if input:
            self.queue_unexpected_data(input)

    def at_command(self, command, noresponse=False, nook=False):
        self.executing_command.set()
        self.check_input()
        self.port.write(command+self.linesep)
        echo = self.port.read(len(command)) #checking for command echo
        if echo != command:
            raise ATError(received=echo, expected=command)
        #print(repr(self.port.read(len(self.linesep)+1))) 
        self.port.read(len(self.linesep)+1) #shifting through the line separator - that +1 seems to be necessary when we're reading right after the echo
        if noresponse: return True #one of commands that doesn't need a response
        answer = self.port.read(self.read_buffer_size)
        self.executing_command.clear()
        lines = filter(None, answer.split(self.linesep))
        #print(lines)
        if nook: return lines
        if self.ok_response not in lines: #expecting OK as one of the elements 
            raise ATError(expected=self.ok_response, received=lines)
        #We can have a sudden undervoltage warning, though
        #I'll assume the OK always goes last in the command
        #So we can pass anything after OK to the unexpected line parser
        ok_response_index = lines.index(self.ok_response)
        if ok_response_index+1 < len(lines):
            self.queue_unexpected_data(lines[(ok_response_index+1):])
            lines = lines[:(ok_response_index+1)]
        if len(lines) == 1: #Single-line response
            if lines[0] == self.ok_response: 
                return True
            else:
                return lines[0]
        else: 
            lines = lines[:-1]
            if len(lines) == 1:
                return lines[0]
            else:
                return lines

    #Functions for background monitoring of any unexpected input

    def queue_unexpected_data(self, data):
        self.unexpected_queue.put(data) 

    def process_incoming_data(self, data):
        logging.debug("Incoming data: {}".format(repr(data)))
        if isinstance(data, str):
            data = data.split(self.linesep)            
        lines = filter(None, data)
        for line in lines:
            #print(line)
            #Now onto the callbacks
            #We should ignore some messages if we're using CLIP
            #As those messages will appear anyway, but processing them 
            #would be redundant. It could be much prettier, though.
            if line == "RING":
                if not self.clcc_enabled:
                    self.on_ring()
                continue
            if line == "BUSY":
                if not self.clcc_enabled:
                    self.on_busy()
                continue
            if line == "HANGUP":
                if not self.clcc_enabled:
                    self.on_hangup()
                continue
            if line == "NO ANSWER":
                if not self.clcc_enabled:
                    self.on_noanswer()
                continue
            if line == "NO CARRIER":
                if not self.clcc_enabled:
                    self.on_nocarrier()
                continue
            if line in ["SMS Ready", "Call Ready"]:
                continue #Modem just reset
            if line.startswith("+CMTI:"):
                self.on_incoming_message(line); continue
            if line.startswith(self.clcc_header):
                self.on_clcc(line); continue
            if line.startswith(self.clip_header):
                self.on_clip(line); continue
            self.parse_unexpected_message(line)
        
    def parse_unexpected_message(self, data):
        #haaaax
        if self.linesep[::-1] in "".join(data):
            lines = "".join(data).split(self.linesep[::-1])
        logging.debug("Unexpected line: {}".format(data))
        print("Unexpected line: {}".format(data))
        
    #The monitor thread - it receives data from the modem and calls callbacks

    def monitor(self):
        while self.should_monitor.isSet():
            #print("Monitoring...")
            if not self.executing_command.isSet():
                #First, the serial port
                #print("Reading data through serial!")
                data = self.port.read(self.read_buffer_size)
                if data: 
                    print("Got data through serial!")
                    self.process_incoming_data(data)
                #Then, the queue of unexpected messages received from other commands
                #print("Reading data from queue!")
                try:
                    data = self.unexpected_queue.get_nowait()
                except Empty:
                    pass
                else:
                    print("Got data from queue!")
                    self.process_incoming_data(data)
            #print("Got to sleep")
            sleep(self.serial_timeout)
            #print("Returned from sleep")
            #try:
            #    print(modem.at_command("AT+CPAS"))
            #except:
            #    print("CPAS exception")
        print("Stopped monitoring!")

    def start_monitoring(self):
        self.should_monitor.set()
        self.thread = Thread(target=self.monitor)
        self.thread.daemon=True
        self.thread.start()

    def stop_monitoring(self):
        self.should_monitor.clear()


if __name__ == "__main__":
    modem = Modem()
    modem.init_modem()
    modem.start_monitoring()
    def dial():
        modem.call("25250034")
    def cpas():
        print(modem.at_command("AT+CPAS"))
