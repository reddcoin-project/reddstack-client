#!/usr/bin/python
"""
    Blockstore-client
    ~~~~~
    copyright: (c) 2014-2015 by Halfmoon Labs, Inc.
    copyright: (c) 2016 by Blockstack.org

    This file is part of Blockstore-client.

    Blockstore-client is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    Blockstore-client is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.
    You should have received a copy of the GNU General Public License
    along with Blockstore-client.  If not, see <http://www.gnu.org/licenses/>.
"""

import random
import json 
import time
import os 
import sys
import traceback
import subprocess
import pprint
import pyreddcoin
import binascii
import logging 
import requests
import keychain 

DEBUG = True

from ConfigParser import SafeConfigParser

# Hack around absolute paths
current_dir = os.path.abspath(os.path.dirname(__file__))
parent_dir = os.path.abspath(current_dir + "/../")

sys.path.insert(0, parent_dir)

AVG_BLOCK_TIME = 600    # average number of seconds between blocks 
CONFIRM_DELAY = 10      # number of blocks to wait to pass before confirming that the name was registered
MAX_UNCONFIRMED = 50000000

def pretty_dump(json_str):
    """ pretty dump
    """
    return json.dumps(json_str, sort_keys=True, indent=4, separators=(',', ': '))


def send_checkpoint( chaincom_client, privkey_str, checkpoint_str="http://blockstack.org/summit" ):
    """
    Write an OP_RETURN to the blockchain, to checkpoint our progress.
    Should be written every Nth name.
    """
    
    nulldata = binascii.hexlify( checkpoint_str )
    return pyreddcoin.embed_data_in_blockchain( nulldata, privkey_str, chaincom_client, 10000, format='hex')


def namecoin_to_bitcoin_address( nmc_address ):
    """
    Convert a namecoin address to a bitcoin address.
    The only difference is the version number.
    """
    
    return pyreddcoin.b58check_encode( pyreddcoin.b58check_decode( nmc_address ), version_byte=0 )


def get_chaincom_api_keys( path="./chaincom.ini" ):
    """
    Read the ini-formatted file given to find chain.com keys.
    """
    
    parser = SafeConfigParser()
    parser.read( path )
    
    return parser.get("chaincom", "api_key_id"), parser.get("chaincom", "api_key_secret")


def get_num_unconfirmed_txs( chaincom_api_key, chaincom_api_secret, address, count=500 ):
    """
    Get the number of unconfirmed transactions for an address.
    """
    r = requests.get("https://api.chain.com/v2/bitcoin/addresses/%s/transactions?limit=%s&api-key-id=%s&api-key-secret=%s" % (address, count, chaincom_api_key, chaincom_api_secret))
    data = None 
    
    if r.status_code != 200:
        return -1 
    
    try:
        data = r.json()
    except:
        print >> sys.stderr, "Failed to get transactions"
        return None 
    
    num_unconfirmed = 0
    for tx in data:
        
        try:
            if tx["confirmations"] == 0:
                num_unconfirmed += 1
        except:
            print tx 
            sys.exit(1)
            
    return num_unconfirmed


def get_balance( chaincom_api_key, chaincom_api_secret, address ):
    """
    Get the number of unconfirmed transactions for an address.
    """
    r = requests.get("https://api.chain.com/v2/bitcoin/addresses/%s?api-key-id=%s&api-key-secret=%s" % (address, chaincom_api_key, chaincom_api_secret))
    data = None 
    
    if r.status_code != 200:
        return -1 
    
    try:
        data = r.json()
    except:
        print >> sys.stderr, "Failed to get transactions"
        return None 
    
    return data[0]["total"]["balance"]
            

def confirm_name_imported( client, name ):
    """
    See if a name has been imported.
    """
    
    name_info = client.lookup( name )
    if 'error' in name_info:
        log.info( "confirm '%s'...no" % name )
        return False 
    
    # must be a full record 
    name_info = name_info[0]
    
    if name_info is None:
        log.info( "confirm '%s'...no" % name )
        return False 
    
    if 'address' not in name_info:
        log.info( "confirm '%s'...no" % name )
        return False 
    
    if 'value_hash' not in name_info:
        log.info( "confirm '%s'...no" % name )
        return False 
    
    if name_info['value_hash'] is None:
        log.info( "confirm '%s'...no" % name )
        return False 
    
    log.info( "confirm '%s'...yes" % name )
    return True
    

def find_imported( client, name_list ):
    """
    Find the list of names that have been imported
    """
    imported = []
    
    for name in name_list:
        if confirm_name_imported( client, name ):
            imported.append( name )
            
    return imported
        

if __name__ == "__main__":
    
    names_json = None
    names = None 
    namespace_id = None
    privkey_str = None 
    pp = pprint.PrettyPrinter()

    if len(sys.argv) != 4:
        print >> sys.stderr, "Usage: %s [json_file] [namespace_id] [private_key]"
        sys.exit(1)

    # try to connect to our broadcast provider
    try:
        chaincom_id, chaincom_secret = get_chaincom_api_keys()
    except Exception, e:
        traceback.print_exc()
        print >> sys.stderr, "Failed to get Chain.com API keys"
        sys.exit(1)
        
    chaincom_client = pyreddcoin.ChainComClient( chaincom_id, chaincom_secret )

    # get our namespace's names
    try:
        with open( sys.argv[1], "r" ) as f:
           names_json = f.read()

    except Exception, e:
        traceback.print_exc()
        print >> sys.stderr, "Failed to read '%s'" % sys.argv[1]
        sys.exit(1)

    privkey_str = sys.argv[3]
    namespace_id = sys.argv[2]
    
    print "--------------------------------------------------------------"
    print "WARN: you will need to populate these keys with BTC beforehand"
    print "--------------------------------------------------------------"
    
    total_balance = 0
    keyring = []
    unfunded = []
    keyring_path = "%s.keyring" % namespace_id 
    
    if os.path.exists(keyring_path):
        print "import from '%s'" % keyring_path
        try:
            tmp = []
            with open( keyring_path, "r" ) as f:
                tmp = f.readlines()
            
            keyring = []
            tmp2 = [k.strip() for k in tmp]
            
            for pk in tmp2:
                addr = pyreddcoin.ReddcoinPrivateKey( pk ).public_key().address()
                balance = get_balance( chaincom_id, chaincom_secret, addr )
                print "%s (%s) balance: %s" % (pk, addr, balance)
                
                total_balance += balance
                if balance > 54000:
                    keyring.append( pk )
                else:
                    unfunded.append(addr)
                
        except Exception, e:
            log.exception(e)
            pass
        
    if len(keyring) == 0:
        pk = pyreddcoin.ReddcoinPrivateKey( privkey_str )
        keyring_generator = keychain.PrivateKeychain.from_private_key( privkey_str )
        
        keyring = [ pk.to_hex() ]
        print "%s (%s) master" % (pk.to_wif(), pk.public_key().address())
        
        for i in xrange(0, 300):
            
            pk_hex = keyring_generator.child(i).private_key()
            pk_wif = pyreddcoin.ReddcoinPrivateKey( pk_hex ).to_wif()
            
            pk_addr = pyreddcoin.ReddcoinPrivateKey( pk_hex ).public_key().address()
            balance = get_balance( chaincom_id, chaincom_secret, pk_addr )
            
            print "%s (%s) balance: %s" % (pk_wif, pk_addr, balance)
            
            total_balance += balance
            if balance >= 54000:
                keyring.append( pk_wif )
            else:
                unfunded.append(pk_addr)
                
        try:
            with open(keyring_path, "w+") as f:
                for k in keyring:
                    f.write("%s\n" % k)
                
                f.flush()
        except Exception, e:
            log.exception(e)
            pass
    
    print "--------------------------------------------------------------"
    
    print "Unfunded:"
    for addr in unfunded:
        print addr
        
    print "--------------------------------------------------------------"
    print "Total: %s" % total_balance
    
    print "--------------------------------------------------------------"
    
    try:
        names = json.loads( names_json )
    except Exception, e:
        traceback.print_exc()
        print >> sys.stderr, "Invalid JSON file '%s'" % sys.argv[1]
        sys.exit(1)

    # record name status
    logfile_path = namespace_id + ".sent"
    failed_path = namespace_id + ".failed"
    confirmed_path = namespace_id + ".confirmed"
    
    sent_names_json = []
    sent_names = {}
    
    confirmed_names = []
    
    unconfirmed_names = {}      # map name to send time
    
    failed_lines = None
    failed = []
    
    num_sent_names = 0
    
    # resume from where we left off...
    try:
        # should contain newline-separated list of names we've processed so far
        if not os.path.exists( logfile_path ):
            sent_fd = open( logfile_path, "w+" )
        else:
            sent_fd = open( logfile_path, "r+" )
        
        if not os.path.exists( failed_path ):
            failed_fd = open( failed_path, "w+" )
        else:
            failed_fd = open( failed_path, "r+" )
        
        if not os.path.exists( confirmed_path ):
            confirmed_fd = open( confirmed_path, "w+" )
        else:
            confirmed_fd = open( confirmed_path, "r+" )
            
        sent_names_json = sent_fd.read().split("\n")
        confirmed_names = confirmed_fd.read().split("\n")
        
        failed = failed_fd.read().split("\n")
        
    except Exception, e:
        traceback.print_exc()
        print >> sys.stderr, "Failed to open '%s'" % logfile_path
        sys.exit(1)

    # get list of sent name records
    for name_json in sent_names_json:
        if len(name_json.strip()) == 0:
            continue
        
        name_rec = json.loads( name_json.strip() )
        sent_names[ name_rec['name'] ] = name_rec
    
    # connect to blockstore
    conf = config.get_config()
    proxy = client.session(conf['blockstored_server'], conf['blockstored_port'])
    
    time_of_last_confirmation = 0 
    
    # find any previously-sent-but-not-confirmed names 
    for sent_name in sent_names.keys():
        if sent_name not in confirmed_names:
            t = sent_names[sent_name].get('time', 0)
            unconfirmed_names[ sent_name ] = t
            
    # sanity check all names 
    for name in names:
        
        # must have BTC or NMC address 
        if not name.has_key('nmc_address') and not name.has_key('btc_address'):
            raise Exception("Name '%s' lacks an address" % name)
        
        # must have a profile hash 
        if not name.has_key('hash') and not name.has_key('profile_hash'):
            raise Exception("Name '%s' lacks a profile hash" % name )
    
    
    # some failed names might have actually gone through.  Find out which.
    new_confirmed = find_imported( client, failed )
    for confirmed_name in new_confirmed:
        confirmed_fd.write( "%s\n" % confirmed_name )
        confirmed_fd.flush()
        
        if confirmed_name in sent_names.keys():
            del sent_names[confirmed_name]
            
        confirmed_names.append( confirmed_name )
        failed.remove( confirmed_name )
        
    # new failed set
    new_failed_fd = open( failed_path + ".tmp", "w+" )
    new_failed_fd.write( "\n".join( failed ) )
    new_failed_fd.flush()
    new_failed_fd.close()
    os.rename( failed_path + ".tmp", failed_path )
    
    key_rr = 0
    
    # do all imports
    for name in names:
        
        username = name['username']
        
        if name.has_key('hash'):
            update_hash = str(name['hash'])
        elif name.has_key('profile_hash'):
            update_hash = str(name['profile_hash'])
            
        fqn = username + "." + namespace_id
        
        if fqn in confirmed_names or fqn in sent_names.keys():
            # already imported or sent
            num_sent_names += 1
            continue 
        
        # how long are we doing to wait?
        delay = 20
        try:
            with open("delay.txt", "r") as fd:
                delay_txt = fd.read()
            
            delay = float(delay_txt.strip())
        except Exception, e:
            print >> sys.stderr, "failed to read delay.txt; assuming %s" % delay
    
        """
        # every so often, see if we need to throttle ourselves
        if num_sent_names % len(keyring) == 0:
            
            total_unconfirmed = 0
            num_unconfirmed_txs = 10000000000
            
            while num_unconfirmed_txs > MAX_UNCONFIRMED:
                
                total_unconfirmed = 0
                
                for pk_str in keyring:
                    
                    addr = pyreddcoin.ReddcoinPrivateKey( pk_str ).public_key().address()
                    total_unconfirmed += get_num_unconfirmed_txs( chaincom_id, chaincom_secret, addr )
                    
                num_unconfirmed_txs = total_unconfirmed
                
                print >> sys.stderr, "%s unconfirmed transactions" % num_unconfirmed_txs
                
                if num_unconfirmed_txs <= MAX_UNCONFIRMED:
                    break
                
                time.sleep(60)
        """
        
        # every block (or on start-up), update the list of imported names
        if time_of_last_confirmation + AVG_BLOCK_TIME < time.time():
            
            log.info( "Check for confirmed names" )
            
            # get sent names that were sent more than AVG_BLOCK_TIME * CONFIRM_DELAY seconds ago 
            names_to_check = filter( lambda n: unconfirmed_names[n] + AVG_BLOCK_TIME * CONFIRM_DELAY < time.time(), unconfirmed_names.keys() )
            
            # which of our unconfirmed names have been confirmed?
            new_confirmed = find_imported( client, names_to_check )
            for confirmed_name in new_confirmed:
                
                confirmed_fd.write( "%s\n" % confirmed_name )
                confirmed_fd.flush()
                
                if confirmed_name in sent_names.keys():
                    del sent_names[confirmed_name]
                    
                confirmed_names.append( confirmed_name )
                
                del unconfirmed_names[ confirmed_name ]
                
            time_of_last_confirmation = time.time()
            
        btc_address = None 
        nmc_address = None 
        address = None
        
        if name.has_key('nmc_address'):
            nmc_address = str(name['nmc_address'])
            btc_address = namecoin_to_bitcoin_address( nmc_address )
            
        elif name.has_key("btc_address"):
            btc_address = name['btc_address']

        # ascii only 
        try:
           fqn = str(fqn)
        except:
           log.debug("non-ascii name '%s'" % fqn)
           continue
          
        count = 0
        MAX_COUNT = len(keyring)
        already_exists = False
        while count < MAX_COUNT:
 
           pk_str = keyring[ key_rr % len(keyring) ]
           pub_str = pyreddcoin.ReddcoinPrivateKey( pk_str ).public_key().address()
           key_rr += 1
           
           existing_name = client.lookup( fqn )
            
           try:
                if existing_name[0] is not None:
                    log.debug("Name '%s' already imported: %s" % (fqn, existing_name))
                
                    confirmed_fd.write( "%s\n" % fqn )
                    confirmed_fd.flush()
                    confirmed_names.append( fqn )
                    already_exists = True
                    break
                    
           except Exception, e:
                log.exception(e)
                sys.exit(0)
           
           log.debug( "name_import " + fqn + " " + btc_address + " " + update_hash + " (key " + pub_str + ")" )
           
           try:
               result = client.name_import( fqn, btc_address, update_hash, pk_str )
           except Exception, e:
               log.error( "register '%s' failed:\n%s\n" % (fqn, traceback.format_exc()) )
      
               if count == 0:      
                  failed_fd.write( "%s\n" % (fqn))
                  failed_fd.flush()

               count += 1
               continue 
        
           if type(result) == type([]):
               result = result[0]
        
           if 'error' in result.keys():
               log.error( "register '%s' failed:\n%s\n" % (fqn, pp.pformat(result)) )
            
               if result['error'] == 'Name already registered':
                   # it's because this is confirmed already!
                   log.debug("Confirmed: '%s'" % fqn)
                   confirmed_fd.write( "%s\n" % fqn)
                   confirmed_fd.flush()
                
                   if fqn in sent_names.keys():
                       del sent_names[fqn]
                
                   confirmed_names.append( fqn )
                
                   if fqn in unconfirmed_names[ fqn ]:
                       del unconfirmed_names[ fqn ]
            
               elif 'has non-base-38 characters' in result['error']:
                  break
                  
               else:
                  print >> sys.stderr, "import failed; retry count %s" % count
                  if count == 0:
                     failed_fd.write( "%s\n" % (fqn))
                     failed_fd.flush()
               
                  if count == MAX_COUNT - 1: 
                     # try again later
                     names.append( name )
                     log.error("result: %s" % result)
                
               count += 1
               continue 
        
           else:
               result['name'] = fqn
               result['time'] = time.time()
               result_str = json.dumps( result )
            
               sent_fd.write( "%s\n" % result_str)
               sent_fd.flush()
             
               print pretty_dump( result )
            
               unconfirmed_names[ fqn ] = result['time']
                
               # record progress
               num_sent_names += 1
               break 
        
        if not already_exists:
            time.sleep(delay)
        """
        if (num_sent_names % 20 == 0):
            
            checkpoint_tx = send_checkpoint( chaincom_client, privkey_str )
            print pretty_dump( checkpoint_tx )
            
            time.sleep(20)
        """

    # wait for all names to confirm 
    while len(unconfirmed_names.keys()) > 0:
        
        time.sleep( AVG_BLOCK_TIME )
    
        # get sent names that were sent more than AVG_BLOCK_TIME * CONFIRM_DELAY seconds ago 
        names_to_check = filter( lambda n: unconfirmed_names[n] + AVG_BLOCK_TIME * CONFIRM_DELAY < time.time(), unconfirmed_names.keys() )
        
        log.info( "Check for %d unconfirmed name(s)" % len(names_to_check) )
        
        # which of our unconfirmed names have been confirmed?
        new_confirmed = find_imported( client, names_to_check )
        for confirmed_name in new_confirmed:
            
            confirmed_fd.write( "%s\n" % confirmed_name )
            confirmed_fd.flush()
            
            if confirmed_name in sent_names.keys():
                del sent_names[confirmed_name]
                
            confirmed_names.append( confirmed_name )
            
            del unconfirmed_names[ confirmed_name ]
