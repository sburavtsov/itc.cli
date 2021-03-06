import os
import logging
import platform
import sys
import json
import getpass
from copy import deepcopy 
from argparse import ArgumentParser

from itc.core.server import ITCServer
from itc.util import *
from itc.conf import *

options = None
config = {}

def __parse_options(args):
    parser = ArgumentParser(description='Command line interface for iTunesConnect.')
    parser.add_argument('--debug', '-d', dest='debug', default=False, action='store_true',
                       help='Debug output')
    parser.add_argument('--username', '-u', dest='username', metavar='USERNAME',
                       help='iTunesConnect username')
    parser.add_argument('--password', '-p', dest='password', metavar='PASSWORD',
                       help='iTunesConnect password')

    group = parser.add_mutually_exclusive_group()

    group.add_argument('--generate-config', '-g', dest='generate_config', default=False, action='store_true',
                       help='Generate initial configuration file based on current applications\' state. \
                       If no --application-id provided, configuration files for all applications will be created.')
    group.add_argument('--config-file', '-c', dest='config_file', type=file,
                       help='Configuration file. For more details on format see https://github.com/kovpas/itc.cli')

    parser.add_argument('--application-version', '-e', dest='application_version', metavar='VERSION', default=None,
                       help='Application version to generate config. \
                       If not provided, config will be generated for latest version')
    parser.add_argument('--application-id', '-a', dest='application_id', type=int, default=-1,
                       help='Application id to process. If --config-file provided and it contains \'application id\', \
                       this property is be ignored')
    parser.add_argument('--generate-config-inapp', '-i', dest='generate_inapp', default=False, action='store_true',
                       help='If this flag passed, inapps will be generated as well. This flag is ignored \
                        if --generate-config is not provided')

    parser.add_argument('--reviews', '-r', dest='reviews', default=False, action='store_true',
                       help='Download reviews')


    args = parser.parse_args(args)
    globals()['options'] = args

    if args.debug == True:
        logging.basicConfig(level=logging.DEBUG)
    else:
        requests_log = logging.getLogger('requests')
        requests_log.setLevel(logging.WARNING)
        
        logging.basicConfig(level=logging.INFO)

    return args

def __parse_configuration_file():
    if options.config_file != None:
        globals()['config'] = json.load(options.config_file)
        ALIASES.language_aliases = globals()['config'].get('config', {}) \
                                .get('language aliases', {})
        ALIASES.device_type_aliases = globals()['config'].get('config', {}) \
                                .get('device type aliases', {})

    return globals()['config']


def flattenDictIndexes(dict):
    for indexKey, val in dict.items():
        if "-" in indexKey:
            startIndex, endIndex = indexKey.split("-")
            for i in range(int(startIndex), int(endIndex) + 1):
                dict[i] = val
            del dict[indexKey]
        else: 
            try:
                dict[int(indexKey)] = val
                del dict[indexKey]
            except:
                pass

    return dict


def main():
    os.umask(0077)
    if not os.path.exists(temp_dir):
        os.mkdir(temp_dir);

    args = __parse_options(sys.argv[1:])
    
    logging.debug('Python %s' % sys.version)
    logging.debug('Running on %s' % platform.platform())
    logging.debug('Temp path = %s' % temp_dir)
    logging.debug('Current Directory = %s' % os.getcwd())

    logging.debug('args %s' % args)

    if options.username == None:
        options.username = raw_input('Username: ')

    server = ITCServer(options.username, options.password)

    if not server.isLoggedIn:
        if options.password == None:
            options.password = getpass.getpass()
        server.login(password = options.password)

    if len(server.applications) == 0:
        server.fetchApplicationsList()

    if len(server.applications) == 0:
        logging.info('No applications found.')
        return
        
    logging.debug(server.applications)
    # logging.debug(options)

    if options.generate_config:
        if options.application_id:
            if options.application_id in server.applications: 
                applications = {}
                applications[options.application_id] = server.applications[options.application_id]
            else:
                logging.error('No application with id ' + str(options.application_id))
                return
        else:
            applications = server.applications

        for applicationId, application in applications.items():
            application.generateConfig(options.application_version, generateInapps = options.generate_inapp)

        return

    if options.reviews:
        if not options.application_id in server.applications: 
            logging.error("Provide correct application id (--application-id or -a option)")
        else:
            application = server.applications[options.application_id]
            application.generateReviews(options.application_version)

    cfg = __parse_configuration_file()
    if len(cfg) == 0:
        logging.info('Nothing to do.')
        return

    applicationDict = cfg['application']
    applicationId = applicationDict.get('id', options.application_id)
    application = None
    commonActions = applicationDict['metadata'].get('general', {})
    specificLangCommands = applicationDict['metadata']['languages']
    langActions = {}
    filename_format = cfg.get('config', {}) \
                           .get('images', {}) \
                              .get('file name format', default_file_format)

    for lang in specificLangCommands:
        langActions[languages.languageNameForId(lang)] = dict_merge(commonActions, specificLangCommands[lang])

    logging.debug(langActions)

    if applicationId in server.applications:
        application = server.applications[applicationId]

        for lang in langActions:
            actions = langActions[lang]
            application.editVersion(actions, lang=lang, filename_format=filename_format)

        for inappDict in applicationDict.get('inapps', {}):
            isIterable = inappDict['id'].find('{index}') != -1
            iteratorDict = inappDict.get('index iterator')

            if isIterable and (iteratorDict == None):
                logging.error('Inapp id contains {index} keyword, but no index_iterator object found. Skipping inapp: ' + inappDict['id'])
                continue

            langsDict = inappDict['languages']
            genericLangsDict = inappDict['general']

            for langId in langsDict:
                langsDict[langId] = dict_merge(genericLangsDict, langsDict[langId])

            inappDict['languages'] = langsDict
            del inappDict['general']

            indexes = [-1]
            if (isIterable):
                indexes = iteratorDict.get('indexes')
                if indexes == None:
                    indexes = range(iteratorDict.get('from', 1), iteratorDict['to'] + 1)

            del inappDict['index iterator']

            for key, value in inappDict.items():
                if (not key in ("index iterator", "general", "languages")) and isinstance(value, dict):
                    flattenDictIndexes(value)

            for langKey, value in inappDict["languages"].items():
                for innerLangKey, langValue in inappDict["languages"][langKey].items():
                    if isinstance(langValue, dict):
                        flattenDictIndexes(langValue)

            realindex = 0
            for index in indexes:
                inappIndexDict = deepcopy(inappDict)
                if isIterable:
                    for key in inappIndexDict:
                        if key in ("index iterator", "general", "languages"):
                            continue

                        if (isinstance(inappIndexDict[key], basestring)):
                            inappIndexDict[key] = inappIndexDict[key].replace('{index}', str(index))
                        elif (isinstance(inappIndexDict[key], list)):
                            inappIndexDict[key] = inappIndexDict[key][realindex]
                        elif (isinstance(inappIndexDict[key], dict)):
                            inappIndexDict[key] = inappIndexDict[key][index]

                    langsDict = inappIndexDict['languages']

                    for langId, langDict in langsDict.items():
                        for langKey in langDict:
                            if (isinstance(langDict[langKey], basestring)):
                                langDict[langKey] = langDict[langKey].replace('{index}', str(index))
                            elif (isinstance(langDict[langKey], list)):
                                langDict[langKey] = langDict[langKey][realindex]
                            elif (isinstance(langDict[langKey], dict)):
                                langDict[langKey] = langDict[langKey][index]

                inapp = application.getInappById(inappIndexDict['id'])
                if inapp == None:
                    application.createInapp(inappIndexDict)
                else:
                    inapp.update(inappIndexDict)

                realindex += 1

