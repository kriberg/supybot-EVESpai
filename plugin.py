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
import psycopg2.pool
import eveapi
import datetime


class EVESpai(callbacks.Plugin):
    """
    EVESpai commands:
    'pos [<system>]' Lists all POSes.
    'evetime' Get current time on Tranquility.
    'whereis <character>' List the location and currently boarded ship of <character>.
    'cache <calltype>' List the cache time of given call type.
    'whoat <system>' List characters and their ships in <system>. If --all is given, ignore the max lines limitation.
    'ship <shiptype>' List characters in <shiptype>.
    'chars <user>' List all characters belonging to <user>
    'price [--location=(<solarsystem>|<region>)] <typeName>' List buy/sell/volume of <type> in <location>, defaults to JIta.
    """
    threaded = True

    def __init__(self, irc):
        self.__parent = super(EVESpai, self)
        self.__parent.__init__(irc)
        self._connect(irc)

    def _connect(self, irc):

        try:
            self.stationspinner = psycopg2.pool.ThreadedConnectionPool(2, 20,
                host=self.registryValue('stationspinner_host'),
                port=self.registryValue('stationspinner_port'),
                dbname=self.registryValue('stationspinner_database'),
                user=self.registryValue('stationspinner_user'),
                password=self.registryValue('stationspinner_password'))
        except Exception, e:
            irc.error('Could not connect to stationspinner database. "{0}"'.format(e))
        try:
            self.sde = psycopg2.pool.ThreadedConnectionPool(2, 20,
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
            cur = self.stationspinner.getconn().cursor()
            cur.execute("""
            SELECT "corporationID"
            FROM corporation_corporationsheet
            WHERE "corporationName"=%s and "enabled"=true
            """, [self.registryValue('corporation')])
            self.corporationID = cur.fetchone()[0]
            cur.close()
        except Exception, e:
            irc.error('Could not find corporation "{0}" in stationspinner database'.format(self.corporation))

    def _sql(self, sql, argslist, single=True, db='stationspinner'):
        conn = getattr(self, db).getconn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        cur.execute(sql, argslist)
        if single:
            data = cur.fetchone()
        else:
            data = cur.fetchall()
        cur.close()
        getattr(self, db).putconn(conn)
        return data


    def _get_SolarSystemID(self, system_name):
        row = self._sql("""SELECT "solarSystemID" FROM "mapSolarSystems"
        WHERE "solarSystemName" ILIKE %s """, [system_name], db='sde')
        return row['solarSystemID']

    def _get_SolarSystem(self, solarSystemID):
        row = self._sql("""SELECT * FROM "mapSolarSystems"
        WHERE "solarSystemID" = %s""", [solarSystemID], db='sde')
        return row

    def _get_locationID(self, location_name):
        row = self._sql("""SELECT "itemID" FROM "mapDenormalize"
        WHERE "itemName" ILIKE %s""", [location_name], db='sde')
        return row['itemID']

    def _get_location(self, locationID):
        row = self._sql("""SELECT * FROM "mapDenormalize"
        WHERE "itemID"=%s""", [locationID], db='sde')
        return row

    def _get_location_by_name(self, locationName):
        row = self._sql("""SELECT * FROM "mapDenormalize"
        WHERE "itemName" ILIKE %s""", [locationName], db='sde')
        return row

    def _get_typeID(self, type_name):
        row = self._sql("""SELECT "typeID" FROM "invTypes"
        WHERE "typeName" ILIKE %s""", [type_name], db='sde')
        return row['typeID']

    def _get_type(self, typeID):
        row = self._sql("""SELECT * FROM "invTypes"
        WHERE "typeID" = %s""", [typeID], db='sde')
        return row

    def _colorize_system(self, location):
        security = location['security']
        if 'solarSystemName' in location:
            name = location['solarSystemName']
        else:
            name = location['itemName']
        if security >= 0.8:
            return ircutils.mircColor(name, fg='teal')
        elif security < 0.8 and security >= 0.6:
            return ircutils.mircColor(name, fg='light green')
        elif security < 0.6 and security >= 0.5:
            return ircutils.mircColor(name, fg='yellow')
        elif security < 0.5 and security >= 0.1:
            return ircutils.mircColor(name, fg='orange')
        elif security < 0.1:
            return ircutils.mircColor(name, fg='red')


    def locationid(self, irc, msg, args, locationName):
        """[<location>]

        Get locationID for a location
        """
        try:
            locationID = self._get_locationID(locationName)
            irc.reply(locationID, prefixNick=False)
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
            irc.reply(typeID, prefixNick=False)
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
            'True': ircutils.mircColor('online', fg='green'),
            'False': ircutils.mircColor('offline', fg='red'),
        }
        irc.reply('{0}, Tranquility is {1} with {2:,d} players logged in'.format(
            ircutils.bold(tq_time.time()),
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

        if system:
            try:
                locationID = self._get_locationID(system)
                solar_system = self._get_SolarSystem(locationID)
            except:
                irc.error('Unknown location')
                return

            rows = self._sql("""
            SELECT *
            FROM corporation_starbase
            WHERE owner_id = %s AND "locationID" = %s""", [self.corporationID,
                                                         locationID], single=False)
        else:
            rows = self._sql("""
            SELECT *
            FROM corporation_starbase
            WHERE owner_id = %s
            ORDER BY "locationID", "moonID" """, [self.corporationID], single=False)
        count = len(rows)

        STATES = {
            0: 	ircutils.mircColor('Unanchored', fg='teal'),           # Also unanchoring? Has valid stateTimestamp.
                                        # Note that moonID is zero for unanchored Towers, but
                                        # locationID will still yield the solar system ID.
            1: 	ircutils.mircColor('Anchored/Offline', fg='orange'),     # No time information stored.
            2: 	ircutils.mircColor('Onlining', fg='light green'), 	        # Will be online at time = onlineTimestamp.
            3: 	ircutils.mircColor('Reinforced', fg='red'),           # Until time = stateTimestamp.
            4: 	ircutils.mircColor('Online', fg='green') 	            # Continuously since time = onlineTimestamp.
        }
        locations = {}
        if system:
            locations[solar_system['solarSystemID']] = solar_system
            irc.reply('Found {0} starbases in {1}'.format(
                             ircutils.bold(count),
                             self._colorize_system(solar_system)),
                      prefixNick=False)
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
                             self._colorize_system(solar_system), #solarsystem
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

        rows = self._sql("""
        SELECT * FROM corporation_membertracking
        WHERE name ILIKE %s AND owner_id=%s""", [character, self.corporationID], single=False)

        if len(rows) > 0:
            for row in rows:
                if row['shipType'] == 'Unknown Type':
                    ship = 'Pod'
                else:
                    ship = row['shipType']
                irc.reply('{0} :: {1} :: {2}'.format(
                    ircutils.bold(row['name']),
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

        call = self._sql("""SELECT * FROM universe_apicall
        WHERE name ILIKE %s AND type='Corporation'""", [apicall])
        if not call:
            irc.error('Unknown APICall')
            return
        else:
            update = self._sql("""
            SELECT * FROM accounting_apiupdate
            WHERE apicall_id=%s AND owner = %s""", [call['id'], self.corporationID])

            if not update['last_update']:
                updated = 'never'
            else:
                updated = update['last_update']
            irc.reply('{0} last updated: {1}'.format(
                call['name'],
                updated
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

        rows = self._sql("""
        SELECT * FROM corporation_membertracking
        WHERE location ILIKE %s AND owner_id=%s""", ['%%{0}%%'.format(system),
                                                     self.corporationID], single=False)
        if len(rows) == 0:
            irc.reply('Found 0 characters in "{0}"'.format(
                system
            ), prefixNick=False)
            return

        if len(rows) <= self.registryValue('max_lines', channel) or ('all', True) in optlist \
                and len(rows) > 0:
            for row in rows:
                if row['shipType'] == 'Unknown Type':
                    ship = 'Pod'
                else:
                    ship = row['shipType']
                irc.reply('{0} :: {1} :: {2}'.format(
                    ircutils.bold(row['name']),
                    self._colorize_system(self._get_location_by_name(row['location'])),
                    ship
                ), prefixNick=False)
        elif len(rows) > self.registryValue('max_lines', channel):
            irc.reply('Found {0} characters in "{1}", but will not name them all'.format(
                len(rows), system
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

        rows = self._sql("""
        SELECT "groupID", "groupName" FROM "invGroups"
        WHERE "categoryID"=6 and "groupName" ILIKE %s""", ['%%{0}%%'.format(shiptype)], db='sde', single=False)

        if len(rows) > 1:
            irc.reply('Found more than one shiptype: "{0}". Be more specific'.format(
                [r['groupName'] for r in rows]
            ), prefixNick=False)
            return

        if len(rows) == 1:
            invGroup = rows[0]
            #find the ships which match the groupID of the ship type
            ships = self._sql("""
            SELECT "typeID", "typeName" FROM "invTypes"
            WHERE "groupID"=%s AND published=true""", [invGroup['groupID']], db='sde', single=False)
            typeIDs = [s['typeID'] for s in ships]
        else:
            # There was no group matching that name, but it could be a specific ship
            invGroup = None
            row = self._get_typeID('%%{0}%%'.format(shiptype))
            if row:
                typeIDs = [row,]
                shiptype = self._get_type(row)['typeName']
            else:
                irc.reply('Unknown shiptype', prefixNick=False)
                return


        rows = self._sql("""
        SELECT * FROM corporation_membertracking
        WHERE owner_id=%s AND "shipTypeID" IN %s""",
                   [self.corporationID, tuple(typeIDs)], single=False)

        if (len(rows) <= self.registryValue('max_lines', channel) or ('all', True) in optlist) \
                and len(rows) > 0:
            irc.reply('Found {0} characters in {1}'.format(
                len(rows),
                invGroup['groupName']
            ), prefixNick=False)
            for row in rows:
                if row['shipType'] == 'Unknown Type':
                    ship = 'Pod'
                else:
                    ship = row['shipType']
                irc.reply('{0} :: {1} :: {2}'.format(
                    ircutils.bold(row['name']),
                    self._colorize_system(self._get_location_by_name(row['location'])),
                    ship
                ), prefixNick=False)
        elif len(rows) > self.registryValue('max_lines', channel):
            irc.reply('Found {0} characters in {1}, but will not name them all'.format(
                len(rows),
                invGroup['groupName']
            ), prefixNick=False)
        else:
            if invGroup:
                shiptype = invGroup['groupName']

            irc.reply('Found {0} characters in {1}'.format(
                len(rows),
                shiptype
            ), prefixNick=False)
    ship = wrap(ship, [optional('channel'),
                       getopts({'all': ''}),
                               'text'])

    def chars(self, irc, msg, args, channel, username):
        """[<channel>] <user>

        List all characters belonging to <user>
        """
        if not self.registryValue('full_access', channel):
            irc.reply('Concord denies you access on this channel!')
            return

        user = self._sql("""
        SELECT * FROM accounting_capsuler
        WHERE username=%s""", [username])
        if not user:
            irc.error('Could not find user "{0}"'.format(username))
            return

        chars = self._sql("""
        SELECT * FROM character_charactersheet
        WHERE owner_id=%s""", [user['id']], single=False)

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
            itemType = self._get_type(typeID)
        except:
            irc.error('Unknown type')
            return

        if len(optlist) == 1:
            location = optlist[0][1]
        else:
            location = 'Jita'

        try:
            locationID = self._get_locationID(location)
            location = self._get_location(locationID)
        except:
            irc.error('Unknown location')
            return

        market = self._sql("""
        SELECT * FROM evecentral_market
        WHERE "locationID"=%s""", [locationID])
        if not market:
            irc.reply('No data for that market location')
            return

        marketitem = self._sql("""
        SELECT * FROM evecentral_marketitem
        WHERE "locationID"=%s AND "typeID"=%s""", [locationID, typeID])
        if marketitem:
            irc.reply('{0} in {1}: buy max: {2} (volume: {3:,d}). sell min: {4} (volume: {5:,d}).'.format(
                ircutils.bold(itemType['typeName']),
                self._colorize_system(location),
                ircutils.mircColor(
                    '{:,.2f}'.format(marketitem['buy_max']),
                    fg='green'),
                int(marketitem['buy_volume']),
                ircutils.mircColor(
                    '{:,.2f}'.format(marketitem['sell_min']),
                    fg='green'),
                int(marketitem['sell_volume']),
            ), prefixNick=False)
        else:
            irc.reply("Prices for {0} in {1} isn't updated yet.".format(
                itemType['typeName'],
                location['itemName']
            ))

    price = wrap(price, [getopts({'location': 'text'}),
                                    'text'])

    def markets(self, irc, msg, args):
        """
        List all price indexed markets.
        """
        locationIDs = self._sql("""
        SELECT "locationID" FROM evecentral_market""", None, single=False)
        if len(locationIDs) == 0:
            irc.reply('No prices have been indexed yet.', prefixNick=False)
            return
        output = []
        for locationID in locationIDs:
            locationID = locationID[0]
            location = self._get_location(locationID)
            if locationID < 30000000:
                # This would be a region
                output.append(ircutils.bold(location['itemName']))
            else:
                output.append(self._colorize_system(location))
        irc.reply(', '.join(output), prefixNick=False)
    markets = wrap(markets)

    def evecommands(self, irc, msg, args):
        """
        Prints an overview of available commands
        """
        desc = """
        EVESpai commands:
        'pos [<system>]' Lists all POSes.
        'evetime' Get current time on Tranquility.
        'whereis <character>' List the location and currently boarded ship of <character>.
        'cache <calltype>' List the cache time of given call type.
        'whoat <system>' List characters and their ships in <system>. If --all is given, ignore the max lines limitation.
        'ship <shiptype>' List characters in <shiptype>.
        'chars <user>' List all characters belonging to <user>
        'price [--location=(<solarsystem>|<region>)] <typeName>' List buy/sell/volume of <type> in <location>, defaults to JIta.
        'markets' List all price indexed markets.
        """
        for line in desc.splitlines():
            irc.reply(line, prefixNick=False)

    evecommands = wrap(evecommands)




Class = EVESpai


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
