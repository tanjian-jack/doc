#! /usr/bin/env python

'''
This script extracts metadata out of bitbake's cache and writes a file
(doc-data.pckl, in Python's pickle format), so that it can be used by
bitbake-metadata2doc.py.

This script is not intended to be manually run by users -- it is
called by bitbake-metadata2doc.sh, which runs it to extract data from
the bitbake's cache for each machine.
'''

import os
import sys

def bitbake_path():
    path = os.environ['PATH'].split(':')
    for dir in path:
        bitbake = os.path.join(dir, 'bitbake')
        if os.path.exists(bitbake):
            return bitbake
    return None

def set_bb_lib_path():
    bitbake = bitbake_path()
    if bitbake:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(bitbake)),
                                        'lib'))
    else:
        sys.stderr.write('bitbake could not be found in $PATH.  Aborting.\n')
        sys.exit(1)

set_bb_lib_path()


import re
import pickle
import logging

import bb.utils
import bb.tinfoil
import bb.cache
from contextlib import closing
from cStringIO import StringIO
import bb.data

class Recipe(object):
    def __init__(self, f, name, ver, layer, ispref):
        self.file = f
        self.name = name
        self.version = ver
        self.layer = layer
        self.is_preferred = ispref

    def __repr__(self):
        return "<Recipe file=%s, name=%s, version=%s, layer=%s, is_preferred=%s>" % (self.file, self.name, self.version, self.layer, self.is_preferred)

def get_layer_name(layerdir):
    return os.path.basename(layerdir.rstrip(os.sep))

def get_file_layer(bbhandler, filename):
    for layer, _, regex, _ in bbhandler.cooker.recipecache.bbfile_config_priorities:
        if regex.match(filename):
            for layerdir in (bbhandler.config_data.getVar('BBLAYERS', True) or "").split():
                if regex.match(os.path.join(layerdir, 'test')) and re.match(layerdir, filename):
                    return get_layer_name(layerdir)
    return "?"

def version_str(pe, pv, pr = None):
    verstr = "%s" % pv
    if pr:
        verstr = "%s-%s" % (verstr, pr)
    if pe:
        verstr = "%s:%s" % (pe, verstr)
    return verstr

def list_recipes(bbhandler, show_overlayed_only=False, show_same_ver_only=False, show_filenames=True, show_multi_provider_only=False):
    pkg_pn = bbhandler.cooker.recipecache.pkg_pn
    (latest_versions, preferred_versions) = bb.providers.findProviders(bbhandler.config_data, bbhandler.cooker.recipecache, pkg_pn)
    allproviders = bb.providers.allProviders(bbhandler.cooker.recipecache)

    # Ensure we list skipped recipes
    # We are largely guessing about PN, PV and the preferred version here,
    # but we have no choice since skipped recipes are not fully parsed
    skiplist = bbhandler.cooker.skiplist.keys()
    skiplist.sort( key=lambda fileitem: bbhandler.cooker.collection.calc_bbfile_priority(fileitem) )
    skiplist.reverse()
    for fn in skiplist:
        recipe_parts = os.path.splitext(os.path.basename(fn))[0].split('_')
        p = recipe_parts[0]
        if len(recipe_parts) > 1:
            ver = (None, recipe_parts[1], None)
        else:
            ver = (None, 'unknown', None)
        allproviders[p].append((ver, fn))
        if not p in pkg_pn:
            pkg_pn[p] = 'dummy'
            preferred_versions[p] = (ver, fn)

    preffiles = []
    items_listed = []
    for p in sorted(pkg_pn):
        if len(allproviders[p]) > 1 or not show_multi_provider_only:
            pref = preferred_versions[p]
            preffile = bb.cache.Cache.virtualfn2realfn(pref[1])[0]
            if preffile not in preffiles:
                preflayer = get_file_layer(bbhandler, preffile)
                multilayer = False
                same_ver = True
                provs = []
                for prov in allproviders[p]:
                    provfile = bb.cache.Cache.virtualfn2realfn(prov[1])[0]
                    provlayer = get_file_layer(bbhandler, provfile)
                    provs.append((provfile, provlayer, prov[0]))
                    if provlayer != preflayer:
                        multilayer = True
                    if prov[0] != pref[0]:
                        same_ver = False

                if (multilayer or not show_overlayed_only) and (same_ver or not show_same_ver_only):
                    items_listed.append(Recipe(preffile, p, version_str(pref[0][0], pref[0][1]), preflayer, True))
                    #print_item(preffile, p, version_str(pref[0][0], pref[0][1]), preflayer, True)
                    for (provfile, provlayer, provver) in provs:
                        if provfile != preffile:
                            items_listed.append(Recipe(provfile, p, version_str(provver[0], provver[1]), provlayer, False))
                            #print_item(provfile, p, version_str(provver[0], provver[1]), provlayer, False)
                    # Ensure we don't show two entries for BBCLASSEXTENDed recipes
                    preffiles.append(preffile)

    return items_listed


def recipe_environment(bbhandler, buildfile):
    ri = bb.cache.CoreRecipeInfo(buildfile, bbhandler.cooker.data)
    fn = None
    envdata = None

    # Parse the configuration here. We need to do it explicitly here since
    # this showEnvironment() code path doesn't use the cache
    bbhandler.cooker.parseConfiguration()

    fn, cls = bb.cache.Cache.virtualfn2realfn(buildfile)
    fn = bbhandler.cooker.matchFile(fn)
    fn = bb.cache.Cache.realfn2virtual(fn, cls)

    try:
        envdata = bb.cache.Cache.loadDataFull(fn, bbhandler.cooker.collection.get_file_appends(fn), bbhandler.cooker.data)
    except Exception as e:
        parselog.exception("Unable to read %s", fn)
        raise

    # emit variables and shell functions
    bb.data.update_data(envdata)
    return envdata


def get_preferred_provider(bbhandler, virtual):
    return bbhandler.config_data.getVar('PREFERRED_PROVIDER_%s' % (virtual,), True)


def load_data(data_file):
    try:
        fd = open(data_file, 'r')
        data = pickle.load(fd)
        fd.close()
        return data
    except:
        return {}

def dump_data(data, data_file):
    fd = open(data_file, 'w')
    pickle.dump(data, fd)
    fd.close()

def format_machine_data(recipe, description):
    return {'recipe': recipe.name,
            'file': recipe.file,
            'version': recipe.version,
            'description': description,
            'layer': recipe.layer}

def usage(exit_code=False):
    print 'Usage: %s <recipe name> ...' % os.path.basename(sys.argv[0])
    if exit_code:
        sys.exit(exit_code)


if '-h' in sys.argv or '-help' in sys.argv or '--help' in sys.argv:
    usage(0)

data_file = sys.argv[1]
user_recipes = sys.argv[2:]

logger = logging.getLogger('BitBake')
bbhandler = bb.tinfoil.Tinfoil()
bbhandler.prepare()
available_recipes = list_recipes(bbhandler)
machine = bbhandler.config_data.getVar('MACHINE', True)
data = load_data(data_file)

for user_recipe in user_recipes:
    for recipe in available_recipes:
        recipe_name = None
        if '/' in user_recipe:
            recipe_name = get_preferred_provider(bbhandler, user_recipe)
        else:
            recipe_name = user_recipe
        if recipe_name and recipe_name == recipe.name:
            env = recipe_environment(bbhandler, recipe.file)
            description = env.getVar('DESCRIPTION', True)
            if not description:
                description = env.getVar('SUMMARY', True)
            if not data.has_key(machine):
                data[machine] = {}
                data[machine]['recipes'] = {}
            data[machine]['recipes'][user_recipe] = format_machine_data(recipe, description)

dump_data(data, data_file)
