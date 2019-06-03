#@author Matthew Abbott
# May 28th, 2019
# This script is for running a shut no shut on any given Cisco switch

import paramiko, time, socket, re, uuid, sys, os, getpass



# this function will return a list of all mac addresses listed when you run the ipconfig /all command
# these mac addresses are used to compare to the mac address table to check to see if the user is using a switch port to connect
# if they are using a switch port then it will retrieve that port and add it to the list it will exclude when doing a shut no shut

def getMacAddress():
    #mac_list is where mac addresses are stored
    mac_list = []
    #if the OS is windows we use cmd to extract the mac addresses 
    # cmd is opened and an ipconfig /all command is executed. Then the lines with physical address at the start are extracted
    if sys.platform == 'win32': 
        for line in os.popen("ipconfig /all"): 
            if line.lstrip().startswith('Physical Address'): 
                mac = line.split(':')[1].strip().replace('-',':')
                mac = mac.replace(':','') 
                #adding the formatted addresses to the mac_list
                mac_list.append(mac) 
    else: 
        for line in os.popen("/sbin/ifconfig"): 
            if line.find('Ether') > -1: 
                mac = line.split()[4] 
                break

    # extracting the blank or irrelevant addresses 
    for m in mac_list:
        if m[0] == '0' and m[1] == '0':
            # the lists and elements are both casted to sets in order to take elements out of the list
            mac_list = set(mac_list) - set(m)
    #return the mac_list so it can be added to the restr_ports list
    return mac_list   

# this function is used for to send commands to the interactive shell and it returns the input in the out variable which stores the output in bytes

def ssh_cmd(shell, out, command):

    shell.send(command)
    #this while loop makes sure the script won't move on until the output is fully spit out of the terminal so we don't have any information loss
    while not channel.recv_ready():
        time.sleep(1)
    #basically this takes the last 9999 characters displayed on the terminal. Later it is decode into ascii characters for readability.
    out = channel.recv(9999)

    #time.sleep(1)

    return out
# this function just is for if you need to run a sequence of commands back to back it calls the original ssh_cmd() function
# there is a wait time of 1 second in between each call of ssh_cmd() to ensure the command goes through properly
def ssh_cmd_list(shell, out, command_list):
    #here tmp_out is initialized as a bytes type to ensure it can take the output of ssh_cmd
    tmp_out = bytes(0)
    for cmd in command_list:
        tmp_out += ssh_cmd(shell, out, cmd)
        time.sleep(1)

    return tmp_out

# this method utilizes the getMacAddress() function and checks for any dynamic mad addresses in the mac address-table that match with the local
# computer's mac addresses. If there is a match it will return a list of ports the script cannot do a shut no shut on
def connected_ports(mac_list, channel, out):
    
    con_port = []
    out = ssh_cmd(channel, out, 'show mac address-table | i DYNAMIC\n')
    for o in out.decode("ascii").splitlines():
        # this if statement is to just cut out the literal command line and the input line that shows up after the information is displayed
        if '|' not in o and '#' not in o:
            #here we are just chopping off the last element of the line that contains the port so we can get the port name
            #the two lines with tmp here are for formatting the mac address because the mac from the switch is formatted differently than
            # the mac address from the local PC
            tmp = o.split()[1].upper()
            tmp = tmp.replace('.','')
            if tmp in mac_list:
                con_port.append(o.split()[len(o.split()) - 1])
    return con_port

print("This is a shut no script ")

# user input
user = input("Enter your username: ")
#this input looks different because it is doesn't display the input because it's a password. It just uses a simple built in library called getpass
pwd = getpass.getpass()
ip = input("Enter the IP: ")
# the restr_ports list contains all ports we want to avoid shutting and no shutting
restr_ports = []
user_ans = input("Do you want to restrict any ports? (y/n): ").lower()

#if the user answers yes this loop activates and we take in as many strings as the user specifies so we know what ports to avoid shutting
if user_ans == 'y':
    while True:
        tmp = input("Enter port you want restricted: (type exit when finished): ")
        if tmp == "exit":
            break
        else:
            restr_ports.append(tmp)

#starting timer for performance tracking
start = time.time()
#establishing a secure shell and connection to the switch

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(ip, username=user, password=pwd)
#ssh.connect('10.10.25.3', username='matthewabbott', password='test')
print("Logged in as: ", user )

channel = ssh.invoke_shell()

out = channel.recv(9999)

#this command makes it so there is no delay when in the output stream to avoid errors
ssh_cmd(channel, out, 'terminal length 0\n')

# ports that are being used by the secure shell to connect are added to the restricted ports list
restr_ports += connected_ports(getMacAddress(), channel, out)

out = ssh_cmd(channel, out, 'show int status\n')
i = 0
# port_strings is for storing the lines with port names that are outputted by 'show int status'
port_strings = []
#ports is for storing the actual port names once we extract them from the port_strings list
ports = []

# this for loop is for extracting the relevant text generated with "show int status". It also adds all relevant lines to the port_strings list
# without the trunking ports included 
tmp_bool = False
for o in out.decode("ascii").splitlines():
    if "Duplex" in o:
        tmp_bool = True
        continue
    elif "#" in o:
        tmp_bool = False
    
    if tmp_bool and "trunk" not in o.lower():
        port_strings.append(o)

#this for loop extracts the port names from port_strings as long as they aren't in the restr_ports list and they aren't port channels (p[0] != 'P')
for port in port_strings:
    i = 0
    for p in port.split():
        i += 1
        if i == 1 and p not in restr_ports and p[0] != 'P':
            ports.append(p)

#configuring the terminal
ssh_cmd(channel, out, 'conf t\n')

# this for loop shuts every port in the ports list
for port in ports:
    print("shutting port: ", port)
    cmd_str = 'int ' + port + '\n'
    ssh_cmd(channel, out, cmd_str)
    ssh_cmd(channel,out, 'shut\n')
    ssh_cmd(channel, out, 'exit\n')
# this is a manual sleep timer to make sure the ports are disconnected for long enough. Time may be subject to change later 
time.sleep(1.5)

# this for loop is for no shutting every port after the sleep timer
for port in ports:
    cmd_str = 'int ' + port + '\n'
    print("no shutting port: ",port)
    ssh_cmd(channel, out, cmd_str)
    ssh_cmd(channel, out, 'no shut\n')
    ssh_cmd(channel,out, 'exit\n')

# exiting out of configure terminal
ssh_cmd(channel,out,'^Z\n')


out = ssh_cmd(channel, out, 'do show ver | i Model\n')


model_num = ""
for o in out.decode("ascii").splitlines():
    if "Model number" in o:
        
        model_num = o.split()[len(o.split()) - 1]


print("MODEL NUMBER: ", model_num)


#closing the connection
ssh.close()

#displaying performance time
end_time = time.time() - start
print("Switch model: ",model_num)
print("It took: " + str(int(end_time))  + " seconds to shut no shut: " + str(len(ports)) + " ports.")