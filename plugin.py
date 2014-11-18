###
# Copyright (c) 2014, Kristian Berg
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

###

import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
import supybot.conf as conf

import psycopg2
import psycopg2.extras
import eveapi
import datetime

# Found the following commands for #evolution
# !stop :: Remove any buffered output for a channel
# !whereat :: Display all pilots in the specified system.
# !help :: List all available commands
# !sov :: Report sovereignty in selected target
# !whois :: Find the owner of the specified character
# !ship :: Returns all pilots flying a specific ship(type)
# !chars :: Determine the characters of an owner
# !gates :: List gates in the specified system
# !evetime :: Returns the current time in EVE
# !pos :: Search for starbases at the given location


class EVESpai(callbacks.Plugin):
    """
    EVESpai commands:
    'pos [<system>]' Lists all POSes. Otionally, only POSes in <system>
    """
    threaded = True

    def __init__(self, irc):
        self.__parent = super(EVESpai, self)
        self.__parent.__init__(irc)
        self._connect(irc)

    def _connect(self, irc):
        try:
            self.stationspinner = psycopg2.connect(
                host=self.registryValue('stationspinner_host'),
                port=self.registryValue('stationspinner_port'),
                dbname=self.registryValue('stationspinner_database'),
                user=self.registryValue('stationspinner_user'),
                password=self.registryValue('stationspinner_password'))
        except Exception, e:
            irc.error('Could not connect to stationspinner database. "{0}"'.format(e))
        try:
            self.sde = psycopg2.connect(
                host=self.registryValue('sde_host'),
                port=self.registryValue('sde_port'),
                dbname=self.registryValue('sde_database'),
                user=self.registryValue('sde_user'),
                password=self.registryValue('sde_password'))
        except Exception, e:
            irc.error('Could not connect to sde database. "{0}"'.format(e))

        if self.registryValue('corporation') == '':
            irc.error('EVESpai requires that you set a corporation')
        try:
            cur = self.stationspinner.cursor()
            cur.execute("""
            SELECT "corporationID"
            FROM corporation_corporationsheet
            WHERE "corporationName"=%s and "enabled"=true
            """, [self.registryValue('corporation')])
            self.corporationID = cur.fetchone()[0]
            cur.close()
        except Exception, e:
            irc.error('Could not find corporation "{0}" in stationspinner database'.format(self.corporation))

    def _get_SolarSystemID(self, system_name):
        cur = self.sde.cursor()
        cur.execute("""SELECT "solarSystemID" FROM "mapSolarSystems"
        WHERE "solarSystemName" ILIKE %s """, [system_name])
        row = cur.fetchone()[0]
        cur.close()
        return row

    def _get_SolarSystem(self, solarSystemID):
        cur = self.sde.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""SELECT * FROM "mapSolarSystems"
        WHERE "solarSystemID" = %s""", [solarSystemID])
        row = cur.fetchone()
        cur.close()
        return row

    def _get_locationID(self, location_name):
        cur = self.sde.cursor()
        cur.execute("""SELECT "itemID" FROM "mapDenormalize"
        WHERE "itemName" ILIKE %s""", [location_name])
        row = cur.fetchone()[0]
        cur.close()
        return row

    def _get_location(self, locationID):
        cur = self.sde.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""SELECT * FROM "mapDenormalize"
        WHERE "itemID"=%s""", [locationID])
        row= cur.fetchone()
        cur.close()
        return row

    def _get_typeID(self, type_name):
        cur = self.sde.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""SELECT "typeID" FROM "invTypes"
        WHERE "typeName" ILIKE %s""", [type_name])
        row= cur.fetchone()[0]
        cur.close()
        return row

    def _get_type(self, typeID):
        cur = self.sde.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""SELECT * FROM "invTypes"
        WHERE "typeID" = %s""", [typeID])
        row= cur.fetchone()
        cur.close()
        return row


    def locationid(self, irc, msg, args, locationName):
        """[<location>]

        Get locationID for a location
        """
        try:
            name = self._get_locationID(locationName)
            irc.reply(name, prefixNick=False)
        except:
            irc.error('Unknown location')

    locationid = wrap(locationid, ['text'])

    def locationname(self, irc, msg, args, locationID):
        """[<location>]

        Get locationName for a location
        """
        try:
            name = self._get_location(locationID)['itemName']
            irc.reply(name, prefixNick=False)
        except:
            irc.error('Unknown location')

    locationname = wrap(locationname, ['text'])

    def typename(self, irc, msg, args, typeID):
        """[<typeID>]

        Get typeName of a typeID
        """
        try:
            name = self._get_type(typeID)['typeName']
            irc.reply(name, prefixNick=False)
        except:
            irc.error('Unknown type')

    typename = wrap(typename, ['text'])

    def typeid(self, irc, msg, args, typeName):
        """[<typeName>]

        Get typeID of a typeName
        """
        try:
            typeID = self._get_typeID(typeName)
            irc.reply(typeID)
        except:
            irc.error('Unknown type')

    typeid = wrap(typeid, ['text'])

    def evetime(self, irc, msg, args):
        """
        Get current time on Tranquility
        """
        api = eveapi.EVEAPIConnection()
        status = api.server.ServerStatus()
        tq_time = datetime.datetime.utcfromtimestamp(status._meta.currentTime)
        SERVER_STATUS = {
            'True': 'online',
            'False': 'offline'
        }
        irc.reply('{0}, Tranquility is {1} with {2} players logged in'.format(
            tq_time.time(),
            SERVER_STATUS[status.serverOpen],
            status.onlinePlayers
        ), prefixNick=False)

    evetime = wrap(evetime, [])
    status = wrap(evetime, [])


    def pos(self, irc, msg, args, channel, system):
        """[<channel>] [<system>]

        List all POSes or all POSes in given system.
        """
        if not self.registryValue('full_access', channel):
            irc.reply('Concord denies you access on this channel!')
            return

        sp = self.stationspinner.cursor(cursor_factory=psycopg2.extras.DictCursor)
        if system:
            try:
                locationID = self._get_locationID(system)
                solar_system = self._get_SolarSystem(locationID)
            except:
                irc.error('Unknown location')
                return

            sp.execute("""
            SELECT *
            FROM corporation_starbase
            WHERE owner_id = %s AND "locationID" = %s""", [self.corporationID,
                                                         locationID])
        else:
            sp.execute("""
            SELECT *
            FROM corporation_starbase
            WHERE owner_id = %s
            ORDER BY "locationID", "moonID" """, [self.corporationID])
        rows = sp.fetchall()
        count = sp.rowcount
        sp.close()

        STATES = {
            0: 	'Unanchored',           # Also unanchoring? Has valid stateTimestamp.
                                        # Note that moonID is zero for unanchored Towers, but
                                        # locationID will still yield the solar system ID.
            1: 	'Anchored/Offline',     # No time information stored.
            2: 	'Onlining', 	        # Will be online at time = onlineTimestamp.
            3: 	'Reinforced',           # Until time = stateTimestamp.
            4: 	'Online' 	            # Continuously since time = onlineTimestamp.
        }
        locations = {}
        if system:
            locations[solar_system['solarSystemID']] = solar_system
            irc.reply('Found {0} starbases in {1}'.format(
                             count,
                             solar_system['solarSystemName']), prefixNick=False)
        else:
            irc.reply('Found {0} starbases'.format(count), prefixNick=False)

        for row in rows:
            try:
                state = STATES[int(row['state'])]
            except:
                state = 'Unknown'
            if not row['locationID'] in locations:
                solar_system = self._get_SolarSystem(row['locationID'])
                locations[solar_system['solarSystemID']] = solar_system
            else:
                solar_system = locations[row['locationID']]

            if not solar_system['regionID'] in locations:
                region = self._get_location(solar_system['regionID'])
                locations[solar_system['regionID']] = region
            else:
                region = locations[solar_system['regionID']]

            irc.reply('{0} :: {1} :: {2} :: {3} :: {4}'.format(
                             region['itemName'],
                             solar_system['solarSystemName'], #solarsystem
                             self._get_location(row['moonID'])['itemName'], #moon
                             self._get_type(int(row['typeID']))['typeName'], #pos type
                             state #offline/online
                             ), prefixNick=False)


    pos = wrap(pos, [optional('channel'), optional('text')])

    def whereis(self, irc, msg, args, channel, character):
        """[<channel>] <character>

        List the location and currently boarded ship of <character>
        """
        if not self.registryValue('full_access', channel):
            irc.reply('Concord denies you access on this channel!')
            return

        sp = self.stationspinner.cursor(cursor_factory=psycopg2.extras.DictCursor)

        sp.execute("""
        SELECT * FROM corporation_membertracking
        WHERE name ILIKE %s AND owner_id=%s""", [character, self.corporationID])

        rows = sp.fetchall()

        if len(rows) > 0:
            for row in rows:
                if row['shipType'] == 'Unknown Type':
                    ship = 'Pod'
                else:
                    ship = row['shipType']
                irc.reply('{0} :: {1} :: {2}'.format(
                    row['name'],
                    row['location'],
                    ship
                ), prefixNick=False)
        else:
            irc.reply('Found 0 characters with a name like "{0}"'.format(character))
    whereis = wrap(whereis, [optional('channel'), 'text'])

    def cache(self, irc, msg, args, channel, apicall):
        """[<channel>] <APICall>

        List the cache time of given endpoint
        """
        if not self.registryValue('full_access', channel):
            irc.reply('Concord denies you access on this channel!')
            return

        sp = self.stationspinner.cursor(cursor_factory=psycopg2.extras.DictCursor)
        sp.execute("""SELECT * FROM universe_apicall
        WHERE name ILIKE %s AND type='Corporation'""", [apicall])
        if sp.rowcount != 1:
            irc.error('Could not find a unique apicall for "{0}"'.format(apicall))
            return
        else:
            call = sp.fetchone()
            sp.execute("""
            SELECT * FROM accounting_apiupdate
            WHERE apicall_id=%s AND owner = %s""", [call['id'], self.corporationID])
            update= sp.fetchone()
            irc.reply('{0} last updated {1}'.format(
                call['name'],
                update['last_update']
            ), prefixNick=False)
    cache = wrap(cache, [optional('channel'), 'text'])

    def whoat(self, irc, msg, args, channel, optlist, system):
        """[<channel>] [--all] <system>

        List characters and their ships in <system>. If --all is given, ignore the max lines
        limitation.
        """
        if not self.registryValue('full_access', channel):
            irc.reply('Concord denies you access on this channel!')
            return

        sp = self.stationspinner.cursor(cursor_factory=psycopg2.extras.DictCursor)


        sp.execute("""
        SELECT * FROM corporation_membertracking
        WHERE location ILIKE %s AND owner_id=%s""", ['%%{0}%%'.format(system),
                                                     self.corporationID])

        rows = sp.fetchall()

        if len(rows) <= self.registryValue('max_lines', channel) or ('all', True) in optlist \
                and len(rows) > 0:
            for row in rows:
                if row['shipType'] == 'Unknown Type':
                    ship = 'Pod'
                else:
                    ship = row['shipType']
                irc.reply('{0} :: {1} :: {2}'.format(
                    row['name'],
                    row['location'],
                    ship
                ), prefixNick=False)
        elif len(rows) > self.registryValue('max_lines', channel):
            irc.reply('Found {0} characters in "{1}", but will not name them all'.format(
                len(rows), system
            ), prefixNick=False)
        else:
            irc.reply('Found 0 characters in "{0}"'.format(
                system
            ), prefixNick=False)
    whoat = wrap(whoat, [optional('channel'),
                         getopts({'all': ''}),
                         'text'])

    def ship(self, irc, msg, args, channel, optlist, shiptype):
        """[<channel>] [--all] <shiptype>

        List characters in <shiptype>. If --all is given, ignore the max lines
        limitation.
        """
        if not self.registryValue('full_access', channel):
            irc.reply('Concord denies you access on this channel!')
            return
        print optlist

        sp = self.stationspinner.cursor(cursor_factory=psycopg2.extras.DictCursor)
        sde = self.sde.cursor(cursor_factory=psycopg2.extras.DictCursor)
        sde.execute("""
        SELECT "groupID", "groupName" FROM "invGroups"
        WHERE "categoryID"=6 and "groupName" ILIKE %s""", ['%%{0}%%'.format(shiptype)])
        rows = sde.fetchall()
        if len(rows) == 0:
            irc.reply('Unknown shiptype', prefixNick=False)
            return
        elif len(rows) > 1:
            irc.reply('Found more than one shiptype: "{0}". Be more specific'.format(
                [r['groupName'] for r in rows]
            ), prefixNick=False)
            return

        shiptype = rows[0]
        #find the ships which match the groupID of the ship type
        sde.execute("""
        SELECT "typeID", "typeName" FROM "invTypes"
        WHERE "groupID"=%s AND published=true""", [shiptype['groupID']])
        ships = sde.fetchall()
        typeIDs = [s['typeID'] for s in ships]
        sp.execute("""
        SELECT * FROM corporation_membertracking
        WHERE owner_id=%s AND "shipTypeID" IN %s""",
                   [self.corporationID, tuple(typeIDs)])
        rows = sp.fetchall()

        if (len(rows) <= self.registryValue('max_lines', channel) or ('all', True) in optlist) \
                and len(rows) > 0:
            irc.reply('Found {0} characters in {1}'.format(
                len(rows),
                shiptype['groupName']
            ), prefixNick=False)
            for row in rows:
                if row['shipType'] == 'Unknown Type':
                    ship = 'Pod'
                else:
                    ship = row['shipType']
                irc.reply('{0} :: {1} :: {2}'.format(
                    row['name'],
                    row['location'],
                    ship
                ), prefixNick=False)
        elif len(rows) > self.registryValue('max_lines', channel):
            irc.reply('Found {0} characters in {1}, but will not name them all'.format(
                len(rows),
                shiptype['groupName']
            ), prefixNick=False)
        else:
            irc.reply('Found {0} characters in {1}'.format(
                len(rows),
                shiptype['groupName']
            ), prefixNick=False)
    ship = wrap(ship, [optional('channel'),
                       getopts({'all': ''}),
                               'text'])

    def chars(self, irc, msg, args, channel, user):
        """[<channel>] <user>

        List all characters belonging to <user>
        """
        if not self.registryValue('full_access', channel):
            irc.reply('Concord denies you access on this channel!')
            return

        sp = self.stationspinner.cursor(cursor_factory=psycopg2.extras.DictCursor)
        sp.execute("""
        SELECT * FROM accounting_capsuler
        WHERE username=%s""", [user])
        if not sp.rowcount == 1:
            irc.error('Could not find user "{0}"'.format(user))
            return
        else:
            user = sp.fetchone()

        sp.execute("""
        SELECT * FROM character_charactersheet
        WHERE owner_id=%s""", [user['id']])

        chars = sp.fetchall()

        if len(chars) == 0:
            irc.reply('User "{0}" has 0 characters registered'.format(user['username']),
                      prefixNick=False)
        else:
            output = []
            for char in chars:
                output.append('{0} [{1}]'.format(
                    char['name'],
                    char['corporationName']
                ))
            irc.reply('Found {0} characters: {1}'.format(
                len(chars),
                ", ".join(output)
            ), prefixNick=False)
    chars = wrap(chars, [optional('channel'), 'text'])

    def price(self, irc, msg, args, optlist, typeName):
        """[--location=(<solarsystem>|<region>)] <typeName>

        Get price of an item at Jita or at a specific solar system/region.
        """
        try:
            typeID = self._get_typeID(typeName)
        except:
            irc.error('Unknown type')

        if len(optlist) == 1:
            location = optlist[0][1]
        else:
            location = 'Jita'

        try:
            locationID = self._get_locationID(location)
        except:
            irc.error('Unknown location')

        sp = self.stationspinner.cursor(cursor_factory=psycopg2.extras.DictCursor)
        sp.execute("""
        SELECT * FROM evecentral_market
        WHERE "locationID"=%s""", [locationID])
        rows = sp.fetchall()
        if len(rows) == 0:
            irc.reply('No data for that market')
            return

        sp.execute("""
        SELECT * FROM evecentral_marketitem
        WHERE "locationID"=%s AND "typeID"=%s""", [locationID, typeID])
        marketitem = sp.fetchone()
        irc.reply('buy max: {0} (volume: {1}). sell min: {2} (volume: {3}).'.format(
            marketitem['buy_max'],
            int(marketitem['buy_volume']),
            marketitem['sell_min'],
            int(marketitem['sell_volume']),
        ))

    price = wrap(price, [getopts({'location': 'text'}),
                                    'text'])





Class = EVESpai


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
