#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""VirusTotal PatrOwl engine application."""

import os
import sys
import json
import time
import hashlib
import threading
import socket
import operator
import random
import logging
from flask import Flask, request, jsonify

# Own library imports
from PatrowlEnginesUtils.PatrowlEngine import _json_serial
from PatrowlEnginesUtils.PatrowlEngine import PatrowlEngine
from PatrowlEnginesUtils.PatrowlEngineExceptions import PatrowlEngineExceptions

# Debug
# from pdb import set_trace as st

app = Flask(__name__)
APP_DEBUG = True
APP_HOST = "0.0.0.0"
APP_PORT = 5007
APP_MAXSCANS = int(os.environ.get('APP_MAXSCANS', 25))
APP_ENGINE_NAME = "virustotal"
APP_BASE_DIR = os.path.dirname(os.path.realpath(__file__))
LOG = logging.getLogger("werkzeug")
VERSION = "1.4.18"

this = sys.modules[__name__]
this.vts = []

engine = PatrowlEngine(
    app=app,
    base_dir=APP_BASE_DIR,
    name=APP_ENGINE_NAME,
    max_scans=APP_MAXSCANS,
    version=VERSION
)

def get_result_ratelimit(asset_name, asset_type):
    """
    This function get the virustotal result and try randomly each apikeys
    In case of error, generally a 204, it retries.
    """
    # Shuffle the virustotal apikeys
    random.shuffle(this.vts)

    count = 0
    vts_engine = this.vts[count]

    if asset_type == "domain":
        result = vts_engine.get_domain_report(this_domain=asset_name)
        while result["response_code"] != 200 and vts_engine != this.vts[-1]:
            count += 1
            vts_engine = this.vts[count]
            result = vts_engine.get_domain_report(this_domain=asset_name)
        if result["response_code"] == 204:
            # Last try, try to wait a minute to reset the time limit
            time.sleep(60)
            result = vts_engine.get_domain_report(this_domain=asset_name)
        if result["response_code"] == 200:
            return result

    elif asset_type == "ip":
        result = vts_engine.get_ip_report(this_ip=asset_name)
        while result["response_code"] != 200 and vts_engine != this.vts[-1]:
            count += 1
            vts_engine = this.vts[count]
            result = vts_engine.get_ip_report(this_ip=asset_name)
        if result["response_code"] == 204:
            # Last try, try to wait a minute to reset the time limit
            time.sleep(60)
            result = vts_engine.get_ip_report(this_ip=asset_name)
        if result["response_code"] == 200:
            return result
    elif asset_type == "url":
        result = vts_engine.get_url_report(this_url=asset_name, scan='1', allinfo='1')
        while result["response_code"] != 200 and vts_engine != this.vts[-1]:
            count += 1
            vts_engine = this.vts[count]
            result = vts_engine.get_url_report(this_url=asset_name, scan='1', allinfo='1')
        if result["response_code"] == 204:
            # Last try, try to wait a minute to reset the time limit
            time.sleep(60)
            result = vts_engine.get_url_report(this_url=asset_name, scan='1', allinfo='1')
        if result["response_code"] == 200:
            return result
    else:
        LOG.error("Wrong asset_type for {}: {}".format(asset_name, asset_type))
        result = dict()

    LOG.error("Wrong response for {}: {}".format(asset_name, result))
    return dict()


@app.errorhandler(404)
def page_not_found(e):
    """Page not found."""
    return engine.page_not_found()


@app.errorhandler(PatrowlEngineExceptions)
def handle_invalid_usage(error):
    """Invalid request usage."""
    response = jsonify(error.to_dict())
    response.status_code = 404
    return response


@app.route('/')
def default():
    """Route by default."""
    return engine.default()


@app.route('/engines/virustotal/')
def index():
    """Return index page."""
    return engine.index()


@app.route('/engines/virustotal/liveness')
def liveness():
    """Return liveness page."""
    return engine.liveness()


@app.route('/engines/virustotal/readiness')
def readiness():
    """Return readiness page."""
    return engine.readiness()


@app.route('/engines/virustotal/test')
def test():
    """Return test page."""
    return engine.test()


@app.route('/engines/virustotal/reloadconfig')
def reloadconfig():
    """Reload the configuration file."""
    res = {"page": "reloadconfig"}
    _loadconfig()
    res.update({"config": {
        "status": engine.status
    }})
    return jsonify(res)


@app.route('/engines/virustotal/info')
def info():
    """Get info on running engine."""
    return engine.info()


@app.route('/engines/virustotal/clean')
def clean():
    """Clean all scans."""
    return engine.clean()


@app.route('/engines/virustotal/clean/<scan_id>')
def clean_scan(scan_id):
    """Clean scan identified by id."""
    return engine.clean_scan(scan_id)


@app.route('/engines/virustotal/status')
def status():
    """Get status on engine and all scans."""
    return engine.getstatus()


@app.route('/engines/virustotal/status/<scan_id>')
def status_scan(scan_id):
    """Get status on scan identified by id."""
    return engine.getstatus_scan(scan_id)


@app.route('/engines/virustotal/stopscans')
def stop():
    """Stop all scans."""
    return engine.stop()


@app.route('/engines/virustotal/stop/<scan_id>')
def stop_scan(scan_id):
    """Stop scan identified by id."""
    return engine.stop_scan(scan_id)


# @app.route('/engines/virustotal/getfindings/<scan_id>')
# def getfindings(scan_id):
#     """Get findings on finished scans."""
#     return engine.getfindings(scan_id)


@app.route('/engines/virustotal/getreport/<scan_id>')
def getreport(scan_id):
    """Get report on finished scans."""
    return engine.getreport(scan_id)


def _loadconfig():
    conf_file = APP_BASE_DIR+'/virustotal.json'
    if os.path.exists(conf_file):
        json_data = open(conf_file)
        engine.scanner = json.load(json_data)
        # sys.path.append(engine.scanner['virustotalapi_bin_path'])
        globals()['virus_total_apis'] = __import__('virus_total_apis')

        this.vts = []
        for apikey in engine.scanner["apikeys"]:
            this.vts.append(virus_total_apis.PrivateApi(apikey))
        del engine.scanner["apikeys"]
        engine.scanner['status'] = "READY"
    else:
        LOG.error("Error: config file '{}' not found".format(conf_file))
        return {"status": "error", "reason": "config file not found"}


@app.route('/engines/virustotal/startscan', methods=['POST'])
def start_scan():
    # @todo: validate parameters and options format
    res = {"page": "startscan"}

    # check the scanner is ready to start a new scan
    if len(engine.scans) == APP_MAXSCANS:
        res.update({
            "status": "error",
            "reason": "Scan refused: max concurrent active scans reached ({})".format(APP_MAXSCANS)
        })
        return jsonify(res)

    status()
    if engine.scanner['status'] != "READY":
        res.update({
            "status": "refused",
            "details": {
                "reason": "scanner not ready",
                "status": engine.scanner['status']
        }})
        return jsonify(res)

    data = json.loads(request.data.decode("UTF-8", "ignore"))
    if 'assets' not in data:
        res.update({
            "status": "refused",
            "details": {
                "reason": "arg error, something is missing ('assets' ?)"
        }})
        return jsonify(res)

    # Sanitize args :
    user_opts = data['options']
    while not isinstance(user_opts, dict):
        user_opts = json.loads(user_opts)

    assets = list()
    for asset in data['assets']:
        if asset not in assets:
            assets.append(asset)

    scan_id = str(data['scan_id'])
    scan = {
        'assets':       assets,
        'threads':      [],
        'options':      user_opts,
        'scan_id':      scan_id,
        'status':       "STARTED",
        'started_at':   int(time.time() * 1000),
        'findings':     {}
    }

    engine.scans.update({scan_id: scan})
    if 'do_scan_ip' in scan['options'] and scan['options']['do_scan_ip']:
        th = threading.Thread(target=_scan_ip, args=(scan_id,))
        th.start()
        engine.scans[scan_id]['threads'].append(th)

    if 'do_scan_domain' in scan['options'] and scan['options']['do_scan_domain']:
        th = threading.Thread(target=_scan_domain, args=(scan_id,))
        th.start()
        engine.scans[scan_id]['threads'].append(th)

    if 'do_scan_url' in scan['options'] and scan['options']['do_scan_url']:
        th = threading.Thread(target=_scan_url, args=(scan_id,))
        th.start()
        engine.scans[scan_id]['threads'].append(th)

    res.update({
        "status": "accepted",
        "details": {
            "scan_id": scan_id
    }})

    return jsonify(res)


def __is_ip_addr(host):
    res = False
    try:
        res = socket.gethostbyname(host) == host
    except Exception:
        pass
    return res


def _scan_ip(scan_id):
    assets = []
    for asset in engine.scans[scan_id]['assets']:
        if asset['datatype'] == "ip" and __is_ip_addr(asset['value']):
            assets.append(asset['value'])

    for asset in assets:
        if asset not in engine.scans[scan_id]["findings"]:
            engine.scans[scan_id]["findings"][asset] = {}
        try:
            engine.scans[scan_id]["findings"][asset]['scan_ip'] = get_result_ratelimit(asset, "ip")
        except Exception as e:
            LOG.error("API Connexion error (quota?) : {}".format(e))
            return False

    return True


def _scan_domain(scan_id):
    assets = []
    for asset in engine.scans[scan_id]['assets']:
        if asset['datatype'] == "domain":
            assets.append(asset['value'])

    for asset in assets:
        if not asset in engine.scans[scan_id]["findings"]:
            engine.scans[scan_id]["findings"][asset] = {}
        try:
            domain_result = get_result_ratelimit(asset, "domain")
            if "detected_urls" in domain_result["results"]:
                count = 0
                for asset_url_dict in domain_result["results"]["detected_urls"]:
                    domain_result["results"]["detected_urls"][count]["report"] = get_result_ratelimit(asset_url_dict['url'], "url")
                    count += 1
            engine.scans[scan_id]["findings"][asset]["scan_domain"] = domain_result
        except Exception as e:
            LOG.error("API Connexion error (quota?) : {}".format(e))
            return False

    return True


def _scan_url(scan_id):
    assets = []
    for asset in engine.scans[scan_id]['assets']:
        if asset['datatype'] == "url":
            assets.append(asset['value'])

    for asset in assets:
        if asset not in engine.scans[scan_id]["findings"].keys():
            engine.scans[scan_id]["findings"][asset] = {}
        try:
            this.vts[random.randint(0,len(this.vts)-1)].scan_url(this_url=asset)
            time.sleep(5)
            engine.scans[scan_id]["findings"][asset]['scan_url'] = get_result_ratelimit(asset, "url")
        except Exception as e:
            LOG.error("API Connexion error (quota?) : {}".format(e))
            return False

    return True


def _parse_results(scan_id):
    issues = []
    summary = {}

    scan = engine.scans[scan_id]
    nb_vulns = {
        "info": 0,
        "low": 0,
        "medium": 0,
        "high": 0
    }
    ts = int(time.time() * 1000)

    for asset in scan["findings"].keys():
        # IP SCAN
        asset_findings = engine.scans[scan_id]["findings"][asset]
        if "scan_ip" in asset_findings and "results" in asset_findings["scan_ip"]:
            results = asset_findings["scan_ip"]["results"]
            if results["response_code"] != 1:
                nb_vulns["info"] += 1
                issues.append({
                    "issue_id": len(issues)+1,
                    "severity": "info", "confidence": "certain",
                    "target": {"addr": [asset], "protocol": "ip"},
                    "title": "IP '{}' not found in VT records".format(asset),
                    "description": "IP '{}' not found in VT records".format(asset),
                    "solution": "n/a",
                    "metadata": {"tags": ["ip"]},
                    "type": "vt_ip_report",
                    "raw": engine.scans[scan_id]['findings'][asset]['scan_ip'],
                    # "raw": scan['findings'][asset]['scan_ip'],
                    "timestamp": ts
                })
            else:
                resolutions_str = ""
                if 'resolutions' in results.keys() and len(results['resolutions']) > 0:
                    # sort by hostname
                    for record in sorted(results['resolutions'], key=operator.itemgetter('hostname')):
                        entry = "{} (last resolved: {})".format(record['hostname'], record['last_resolved'])
                        resolutions_str = "".join((resolutions_str, entry+"\n"))
                    resolutions_hash = hashlib.sha1(str(resolutions_str).encode('utf-8')).hexdigest()[:6]

                    nb_vulns['info'] += 1
                    issues.append({
                        "issue_id": len(issues)+1,
                        "severity": "info", "confidence": "certain",
                        "target": {"addr": [asset], "protocol": "ip"},
                        "title": "Resolved hostnames for '{}' (#: {}, HASH: {})".format(asset, len(results['resolutions']), resolutions_hash),
                        "description": "Hostnames that have resolved to this IP address. VirusTotal resolve it when a file or URL related to this IP address is seen:\n{}".format(
                            resolutions_str),
                        "solution": "n/a",
                        "metadata": {"tags": ["ip", "detection"]},
                        "type": "ip_resolutions",
                        "raw": {"resolutions": results['resolutions']},
                        "timestamp": ts
                    })

                detected_url_str = ""
                if 'detected_urls' in results.keys() and len(results['detected_urls']) > 0:
                    # sort by url
                    for record in sorted(results['detected_urls'], key=operator.itemgetter('url')):
                        entry = "{} (total: {}, scan date: {})".format(record['url'], record['total'], record['scan_date'])
                        detected_url_str = "".join((detected_url_str, entry+"\n"))
                    detected_url_hash = hashlib.sha1(str(detected_url_str).encode('utf-8')).hexdigest()[:6]

                    nb_vulns['info'] += 1
                    issues.append({
                        "issue_id": len(issues)+1,
                        "severity": "info", "confidence": "certain",
                        "target": {"addr": [asset], "protocol": "ip"},
                        "title": "URLs hosted at '{}' (#: {}, HASH: {})".format(asset, len(results['detected_urls']), detected_url_hash),
                        "description": "URLs hosted at this IP address that have url scanner postive detections:\n{}".format(
                            detected_url_str),
                        "solution": "n/a",
                        "metadata": {"tags": ["ip", "url"]},
                        "type": "ip_detected_urls",
                        "raw": {"detected_urls": results['detected_urls']},
                        "timestamp": ts
                    })

                undetected_samples_str = ""
                if 'undetected_downloaded_samples' in results.keys() and len(results['undetected_downloaded_samples']) > 0:
                    # sort by sha256
                    for record in sorted(results['undetected_downloaded_samples'], key=operator.itemgetter('sha256')):
                        entry = "{} (total: {}, positives: {})".format(
                            record['sha256'], record['total'], record['positives'])
                        undetected_samples_str = "".join((undetected_samples_str, entry+"\n"))
                    undetected_samples_hash = hashlib.sha1(str(undetected_samples_str).encode('utf-8')).hexdigest()[:6]

                    nb_vulns['low'] += 1
                    issues.append({
                        "issue_id": len(issues)+1,
                        "severity": "low", "confidence": "certain",
                        "target": {"addr": [asset], "protocol": "ip"},
                        "title": "Downloaded files from '{}', with no antivirus detections (#: {}, HASH: {})".format(asset, len(results['undetected_downloaded_samples']), undetected_samples_hash),
                        "description": "Latest 100 files that have been downloaded from this IP address, with no antivirus detections:\n{}".format(
                            undetected_samples_str),
                        "solution": "n/a",
                        "metadata": {"tags": ["ip", "samples"]},
                        "type": "ip_undetected_samples",
                        "raw": {"undetected_downloaded_samples": results['undetected_downloaded_samples']},
                        "timestamp": ts
                    })

                detected_samples_str = ""
                if 'detected_communicating_samples' in results.keys() and len(results['detected_communicating_samples']) > 0:
                    # sort by sha256
                    for record in sorted(results['detected_communicating_samples'], key=operator.itemgetter('sha256')):
                        entry = "{} (total: {}, positives: {})".format(
                            record['sha256'], record['total'], record['positives'])
                        detected_samples_str = "".join((detected_samples_str, entry+"\n"))
                    detected_samples_hash = hashlib.sha1(str(detected_samples_str).encode('utf-8')).hexdigest()[:6]

                    nb_vulns['high'] += 1
                    issues.append({
                        "issue_id": len(issues)+1,
                        "severity": "high", "confidence": "certain",
                        "target": {"addr": [asset], "protocol": "ip"},
                        "title": "Files communicating with '{}' when sandboxed (#: {}, HASH: {})".format(asset, len(results['detected_communicating_samples']), detected_samples_hash),
                        "description": "Latest 100 files submitted to VirusTotal that are detected by one or more antivirus solutions and communicate with the IP address provided when executed in a sandboxed environment:\n{}".format(
                            detected_samples_str),
                        "solution": "n/a",
                        "metadata": {"tags": ["ip", "samples"]},
                        "type": "ip_detected_samples",
                        "raw": {"detected_communicating_samples": results['detected_communicating_samples']},
                        "timestamp": ts
                    })

                # as info
                nb_vulns['info'] += 1
                as_info = "ASN: {}\nAS Owner: {}\nCountry: {}".format(results['asn'], results['as_owner'], results['country'])
                issues.append({
                    "issue_id": len(issues)+1,
                    "severity": "info", "confidence": "certain",
                    "target": {"addr": [asset], "protocol": "ip"},
                    "title": "ASN info for '{}' (ASN: {})".format(asset, results['asn']),
                    "description": "ASN info for '{}':\n{}".format(
                        asset, as_info),
                    "solution": "n/a",
                    "metadata": {"tags": ["ip", "asn", "country"]},
                    "type": "ip_asn",
                    "raw": {"asn": results['asn'], "as_owner": results['as_owner'], "country": results['country']},
                    "timestamp": ts
                })

                # all findings
                ip_data = "".join((asset,as_info,resolutions_str,detected_url_str,undetected_samples_str,detected_samples_str))
                ip_hash = detected_samples_hash = hashlib.sha1(str(ip_data).encode('utf-8')).hexdigest()[:6]
                nb_vulns['info'] += 1
                issues.append({
                    "issue_id": len(issues)+1,
                    "severity": "info", "confidence": "certain",
                    "target": {"addr": [asset], "protocol": "ip"},
                    "title": "[Scan Summary] IP report for '{}' (HASH: {})".format(asset, ip_hash),
                    "description": "IP Report for '{}':\n\n{}\n\nResolutions: \n{}\n\nDetected URLs: \n{}\n\nFiles downloaded w/o antivirus detection: \n{}\n\nFiles communicating with the asset: \n{}".format(
                        asset, as_info, resolutions_str, detected_url_str,
                        undetected_samples_str, detected_samples_str),
                    "solution": "n/a",
                    "metadata": {
                        "tags": ["ip"],
                        "links": ["https://www.virustotal.com/en/ip-address/{}/information/".format(asset)]},
                    "type": "ip_report",
                    "raw": results,
                    "timestamp": ts
                })

        # DOMAIN SCAN
        if 'scan_domain' in engine.scans[scan_id]['findings'][asset].keys() and 'results' in engine.scans[scan_id]['findings'][asset]['scan_domain']:
            results = engine.scans[scan_id]['findings'][asset]['scan_domain']['results']
            if results['response_code'] != 1:
                nb_vulns['info'] += 1
                issues.append({
                    "issue_id": len(issues)+1,
                    "severity": "info", "confidence": "certain",
                    "target": {"addr": [asset], "protocol": "domain"},
                    "title": "Domain '{}' not found in VT records".format(asset),
                    "description": "Domain '{}' not found in VT records".format(asset),
                    "solution": "n/a",
                    "metadata": {"tags": ["domain"]},
                    "type": "vt_domain_report",
                    "raw": engine.scans[scan_id]['findings'][asset]['scan_domain'],
                    "timestamp": ts
                })
            else:
                # categories
                domain_categories = ""
                if 'categories' in results.keys() and len(results['categories']) > 0:
                    domain_categories = ", ".join(sorted(results['categories']))
                    nb_vulns['info'] += 1
                    issues.append({
                        "issue_id": len(issues)+1,
                        "severity": "info", "confidence": "certain",
                        "target": {"addr": [asset], "protocol": "domain"},
                        "title": "Domain categories for '{}': '{}'".format(asset, domain_categories),
                        "description": "Domain categories (BitDefender, Websense ThreatSeeker, ...): '{}'".format(domain_categories),
                        "solution": "n/a",
                        "metadata": {"tags": ["domain", "categories"]},
                        "type": "domain_categories",
                        "raw": {"categories": results['categories']},
                        "timestamp": ts
                    })

                #whois
                domain_whois = ""
                if 'whois' in results.keys() and results['whois'] is not None:
                    nb_vulns['info'] += 1
                    issues.append({
                        "issue_id": len(issues)+1,
                        "severity": "info", "confidence": "certain",
                        "target": {"addr": [asset], "protocol": "domain"},
                        "title": "Domain whois for '{}' (HASH: {})".format(
                            asset, hashlib.sha1(str(results['whois']).encode('utf-8')).hexdigest()[:6]),
                        "description": "Domain whois for '{}':\n\n{}".format(
                            asset, results['whois']),
                        "solution": "n/a",
                        "metadata": {"tags": ["domain", "whois"]},
                        "type": "domain_whois",
                        "raw": {"whois": results['whois']},
                        "timestamp": ts
                    })

                # domain_siblings
                domain_siblings_str = ""
                if 'domain_siblings' in results.keys() and len(results['domain_siblings']) > 0:
                    for record in sorted(results['domain_siblings']):
                        domain_siblings_str = "".join((domain_siblings_str, record+"\n"))
                    domain_siblings_hash = hashlib.sha1(str(domain_siblings_str).encode('utf-8')).hexdigest()[:6]
                    nb_vulns['info'] += 1
                    issues.append({
                        "issue_id": len(issues)+1,
                        "severity": "info", "confidence": "certain",
                        "target": {"addr": [asset], "protocol": "domain"},
                        "title": "Domain siblings found for '{}' (HASH: {})".format(
                            asset, domain_siblings_hash),
                        "description": "Domain siblings found for'{}':\n\n{}".format(
                            asset, domain_siblings_str),
                        "solution": "n/a",
                        "metadata": {"tags": ["domain", "siblings"]},
                        "type": "domain_siblings",
                        "raw": {"domain_siblings": sorted(results['domain_siblings'])},
                        "timestamp": ts
                    })

                # resolutions
                resolutions_str = ""
                if 'resolutions' in results.keys() and len(results['resolutions']) > 0:
                    # sort by hostname
                    for record in sorted(results['resolutions'], key=operator.itemgetter('ip_address')):
                        entry = "{} (last resolved: {})".format(record['ip_address'], record['last_resolved'])
                        resolutions_str = "".join((resolutions_str, entry+"\n"))
                    resolutions_hash = hashlib.sha1(str(resolutions_str).encode('utf-8')).hexdigest()[:6]

                    nb_vulns['info'] += 1
                    issues.append({
                        "issue_id": len(issues)+1,
                        "severity": "info", "confidence": "certain",
                        "target": {"addr": [asset], "protocol": "domain"},
                        "title": "Resolved IPs for '{}' (#: {}, HASH: {})".format(asset, len(results['resolutions']), resolutions_hash),
                        "description": "IPs that have been resolved to this domain address. VirusTotal resolve it when a file or URL related to this IP address is seen:\n{}".format(
                            resolutions_str),
                        "solution": "n/a",
                        "metadata": {"tags": ["domain", "resolution"]},
                        "type": "domain_resolutions",
                        "raw": {"domain_siblings": results['resolutions']},
                        "timestamp": ts
                    })

                # subdomains
                subdomains_str = ""
                if 'subdomains' in results.keys() and len(results['subdomains']) > 0:
                    # sort by hostname
                    for record in sorted(results['subdomains']):
                        subdomains_str = "".join((subdomains_str, record+"\n"))
                    subdomains_hash = hashlib.sha1(str(subdomains_str).encode('utf-8')).hexdigest()[:6]

                    nb_vulns['info'] += 1
                    issues.append({
                        "issue_id": len(issues)+1,
                        "severity": "info", "confidence": "certain",
                        "target": {"addr": [asset], "protocol": "domain"},
                        "title": "Subdomains found for '{}' (HASH: {})".format(asset, subdomains_hash),
                        "description": "Subdomains found for '{}':\n\n{}".format(
                            asset, subdomains_str),
                        "solution": "n/a",
                        "metadata": {"tags": ["domain", "subdomains"]},
                        "type": "subdomain_list",
                        "raw": {"subdomain_list": sorted(results['subdomains'])},
                        "timestamp": ts
                    })

                # detected_urls
                detected_url_str = ""
                if 'detected_urls' in results.keys() and len(results['detected_urls']) > 0:
                    # sort by url
                    for record in sorted(results['detected_urls'], key=operator.itemgetter('url')):
                        entry = "{} (total: {}, scan date: {})".format(record['url'], record['total'], record['scan_date'])
                        detected_url_str = "".join((detected_url_str, entry+"\n"))
                        if "results" in record["report"] and "positives" in record["report"]["results"] and record["report"]["results"]["positives"] > 0:
                            url_hash = hashlib.sha1(str(record["url"]).encode('utf-8')).hexdigest()[:6]
                            nb_vulns['high'] += 1
                            issues.append({
                                "issue_id": len(issues)+1,
                                "severity": "high", "confidence": "certain",
                                "target": {"addr": [asset], "protocol": "url"},
                                "title": "URL scan detected at least 1 positive match (Score: {}/{}, HASH: {})".format(
                                    record["report"]["results"]["positives"], record["report"]["results"]["total"], url_hash),
                                "description": "URL report for '{}' stated at least 1 positive match ({}/{}):\n\n{}".format(
                                    record["url"], record["report"]["results"]["positives"], record["report"]["results"]["total"], record["report"]["results"]["permalink"]),
                                "solution": "n/a",
                                "metadata": {"tags": ["url"], "links": [record["report"]["results"]["permalink"]]},
                                "type": "vt_url_positivematch",
                                "raw": {"detected_urls": results['detected_urls']},
                                "timestamp": ts
                            })

                    detected_url_hash = hashlib.sha1(str(detected_url_str).encode('utf-8')).hexdigest()[:6]

                    nb_vulns['info'] += 1
                    issues.append({
                        "issue_id": len(issues)+1,
                        "severity": "info", "confidence": "certain",
                        "target": {"addr": [asset], "protocol": "domain"},
                        "title": "URLs hosted at '{}' (#: {}, HASH: {})".format(asset, len(results['detected_urls']), detected_url_hash),
                        "description": "URLs hosted at this domain address that have url scanner postive detections:\n{}".format(
                            detected_url_str),
                        "solution": "n/a",
                        "metadata": {"tags": ["domain", "url"]},
                        "type": "domain_detected_urls",
                        "raw": {"detected_urls": results['detected_urls']},
                        "timestamp": ts
                    })

                # detected_communicating_samples
                detected_samples_str = ""
                if 'detected_communicating_samples' in results.keys() and len(results['detected_communicating_samples']) > 0:
                    # sort by sha256
                    for record in sorted(results['detected_communicating_samples'], key=operator.itemgetter('sha256')):
                        entry = "{} (total: {}, positives: {})".format(
                            record['sha256'], record['total'], record['positives'])
                        detected_samples_str = "".join((detected_samples_str, entry+"\n"))
                    detected_samples_hash = hashlib.sha1(str(detected_samples_str).encode('utf-8')).hexdigest()[:6]

                    nb_vulns['high'] += 1
                    issues.append({
                        "issue_id": len(issues)+1,
                        "severity": "high", "confidence": "certain",
                        "target": {"addr": [asset], "protocol": "domain"},
                        "title": "Files communicating with '{}' when sandboxed (HASH: {})".format(asset, detected_samples_hash),
                        "description": "Latest 100 files submitted to VirusTotal that are detected by one or more antivirus solutions and communicate with the domain address provided when executed in a sandboxed environment:\n{}".format(
                            detected_samples_str),
                        "solution": "n/a",
                        "metadata": {"tags": ["domain", "samples"]},
                        "type": "ip_detected_samples",
                        "raw": {"detected_communicating_samples": results['detected_communicating_samples']},
                        "timestamp": ts
                    })

                # undetected_downloaded_samples
                undetected_samples_str = ""
                if 'undetected_downloaded_samples' in results.keys() and len(results['undetected_downloaded_samples']) > 0:
                    # sort by sha256
                    undetected_referrer_samples_links = []
                    for record in sorted(results['undetected_downloaded_samples'], key=operator.itemgetter('sha256')):
                        link = "https://www.virustotal.com/#/file/{}".format(record['sha256'])
                        entry = "{} (total: {}, positives: {})".format(
                            link, record['total'], record['positives'])
                        undetected_referrer_samples_links.append(link)
                        undetected_samples_str = "".join((undetected_samples_str, entry+"\n"))
                    undetected_samples_hash = hashlib.sha1(str(undetected_samples_str).encode('utf-8')).hexdigest()[:6]

                    nb_vulns['low'] += 1
                    issues.append({
                        "issue_id": len(issues)+1,
                        "severity": "low", "confidence": "certain",
                        "target": {"addr": [asset], "protocol": "domain"},
                        "title": "Downloaded files from '{}', with no antivirus detections (HASH: {})".format(asset, undetected_samples_hash),
                        "description": "Latest 100 files that have been downloaded from this domain address, with no antivirus detections:\n{}".format(
                            undetected_samples_str),
                        "solution": "n/a",
                        "metadata": {
                            "tags": ["domain", "samples"],
                            "links": undetected_referrer_samples_links
                        },
                        "type": "ip_undetected_samples",
                        "raw": {"undetected_downloaded_samples": results['undetected_downloaded_samples']},
                        "timestamp": ts
                    })

                # detected_referrer_samples
                detected_referrer_samples_str = ""
                if 'detected_referrer_samples' in results.keys() and len(results['detected_referrer_samples']) > 0:
                    # sort by sha256

                    detected_referrer_samples_links = []
                    for record in sorted(results['detected_referrer_samples'], key=operator.itemgetter('sha256')):
                        link = "https://www.virustotal.com/#/file/{}".format(record['sha256'])
                        entry = "{} (total: {}, positives: {})".format(
                            link, record['total'], record['positives'])
                        detected_referrer_samples_links.append(link)
                        detected_referrer_samples_str = "".join((detected_referrer_samples_str, entry+"\n"))
                    detected_referrer_samples_hash = hashlib.sha1(str(detected_referrer_samples_str).encode('utf-8')).hexdigest()[:6]

                    nb_vulns['high'] += 1
                    issues.append({
                        "issue_id": len(issues)+1,
                        "severity": "high", "confidence": "certain",
                        "target": {"addr": [asset], "protocol": "domain"},
                        "title": "Downloaded files containing '{}' among their strings, with antivirus detections (HASH: {})".format(asset, detected_referrer_samples_hash),
                        "description": "100 Most recent samples that contain the given domain among their strings and detected by at least one AV:\n{}".format(
                            detected_referrer_samples_str),
                        "solution": "n/a",
                        "metadata": {
                            "tags": ["domain", "samples", "malware"],
                            "links": detected_referrer_samples_links },
                        "type": "domain_detected_referrer_samples",
                        "raw": {"detected_referrer_samples": results['detected_referrer_samples']},
                        "timestamp": ts
                    })
                # undetected_referrer_samples -> medium
                undetected_referrer_samples_str = ""
                if 'undetected_referrer_samples' in results.keys() and len(results['undetected_referrer_samples']) > 0:
                    # sort by sha256
                    undetected_referrer_samples_links = []
                    for record in sorted(results['undetected_referrer_samples'], key=operator.itemgetter('sha256')):
                        link = "https://www.virustotal.com/#/file/{}".format(record['sha256'])
                        entry = "{} (positives: {}, total: {})".format(
                            link, record['positives'], record['total'])
                        undetected_referrer_samples_links.append(link)
                        undetected_referrer_samples_str = "".join((undetected_referrer_samples_str, entry+"\n"))
                    undetected_referrer_samples_hash = hashlib.sha1(str(undetected_referrer_samples_str).encode('utf-8')).hexdigest()[:6]

                    nb_vulns['low'] += 1
                    issues.append({
                        "issue_id": len(issues)+1,
                        "severity": "medium", "confidence": "certain",
                        "target": {"addr": [asset], "protocol": "domain"},
                        "title": "Downloaded files containing '{}' among their strings, with partial antivirus detections (HASH: {})".format(asset, undetected_referrer_samples_hash),
                        "description": "100 Most recent samples that contain the given domain among their strings and not detected by at least one AV:\n{}".format(
                            undetected_referrer_samples_str),
                        "solution": "n/a",
                        "metadata": {
                            "tags": ["domain", "samples", "malware"],
                            "links": undetected_referrer_samples_links
                        },
                        "type": "domain_undetected_referrer_samples",
                        "raw": {"undetected_referrer_samples": results['undetected_referrer_samples']},
                        "timestamp": ts
                    })

                pcaps_str = ""
                if 'pcaps' in results.keys() and len(results['pcaps']) > 0:
                    # sort by hostname
                    for record in sorted(results['pcaps']):
                        pcaps_str = "".join((pcaps_str, record+"\n"))
                    pcaps_hash = hashlib.sha1(str(pcaps_str).encode('utf-8')).hexdigest()[:6]

                    nb_vulns['medium'] += 1
                    issues.append({
                        "issue_id": len(issues)+1,
                        "severity": "medium", "confidence": "certain",
                        "target": {"addr": [asset], "protocol": "domain"},
                        "title": "Pcaps found for '{}' (HASH: {})".format(asset, pcaps_hash),
                        "description": "Pcaps found for '{}':\n\n{}".format(
                            asset, pcaps_str),
                        "solution": "n/a",
                        "metadata": {"tags": ["domain", "pcap"]},
                        "type": "domain_pcaps",
                        "raw": {"pcaps": sorted(results['pcaps'])},
                        "timestamp": ts
                    })

                # WOT domain info
                wot_str = ""
                if 'WOT domain info' in results.keys() and len(results['WOT domain info']) > 0:
                    # sort by hostname
                    for record_key in sorted(results['WOT domain info'].keys()):
                        line = str(record_key)+": "+str(results['WOT domain info'][record_key])+"\n"
                        wot_str = "".join((wot_str, line))
                    wot_hash = hashlib.sha1(str(wot_str).encode('utf-8')).hexdigest()[:6]

                    nb_vulns['info'] += 1
                    issues.append({
                        "issue_id": len(issues)+1,
                        "severity": "info", "confidence": "certain",
                        "target": {"addr": [asset], "protocol": "domain"},
                        "title": "Web-Of-Trust (WOT) info for '{}' (HASH: {})".format(asset, wot_hash),
                        "description": "Web-Of-Trust (WOT) info for '{}':\n\n{}".format(
                            asset, wot_str),
                        "solution": "n/a",
                        "metadata": {"tags": ["domain", "wot", "reputation"]},
                        "type": "domain_wot_info",
                        "raw": {"wot_info": results['WOT domain info']},
                        "timestamp": ts
                    })

                    # WOT analysis
                    for record_key in results['WOT domain info'].keys():
                        if results['WOT domain info'][record_key] == "Excellent": continue
                        elif results['WOT domain info'][record_key] == "Good":
                            nb_vulns['medium'] += 1
                            issues.append({
                                "issue_id": len(issues)+1,
                                "severity": "medium", "confidence": "certain",
                                "target": {"addr": [asset], "protocol": "domain"},
                                "title": "Web-Of-Trust (WOT) reputation level of '{}' is 'Good'".format(asset),
                                "description": "Web-Of-Trust (WOT) reputation level of '{}' is 'Good':\n\n{}".format(
                                    asset, wot_str),
                                "solution": "n/a",
                                "metadata": {"tags": ["domain", "wot", "reputation"]},
                                "type": "domain_wot_badlevel",
                                "raw": {"wot_info": results['WOT domain info']},
                                "timestamp": ts
                            })
                        else:
                            nb_vulns['high'] += 1
                            issues.append({
                                "issue_id": len(issues)+1,
                                "severity": "high", "confidence": "certain",
                                "target": {"addr": [asset], "protocol": "domain"},
                                "title": "Web-Of-Trust (WOT) reputation level of '{}' is '{}'".format(asset, results['WOT domain info'][record_key]),
                                "description": "Web-Of-Trust (WOT) reputation level of '{}' is '{}':\n\n{}".format(
                                    asset, results['WOT domain info'][record_key], wot_str),
                                "solution": "n/a",
                                "metadata": {"tags": ["domain", "wot", "reputation"]},
                                "type": "domain_wot_badlevel",
                                "raw": {"wot_info": results['WOT domain info']},
                                "timestamp": ts
                            })

                # Webutation domain info
                webutation_str = ""
                if 'Webutation domain info' in results.keys() and len(results['Webutation domain info']) > 0:
                    # sort by hostname
                    for record_key in sorted(results['Webutation domain info'].keys()):
                        line = str(record_key)+": "+str(results['Webutation domain info'][record_key])+"\n"
                        webutation_str = "".join((webutation_str, line))
                    webutation_hash = hashlib.sha1(str(webutation_str).encode('utf-8')).hexdigest()[:6]

                    nb_vulns['info'] += 1
                    issues.append({
                        "issue_id": len(issues)+1,
                        "severity": "info", "confidence": "certain",
                        "target": {"addr": [asset], "protocol": "domain"},
                        "title": "Webutation info for '{}' (Verdict: {}, HASH: {})".format(
                            asset, results['Webutation domain info']['Verdict'], webutation_hash),
                        "description": "Webutation info for '{}':\n\n{}".format(
                            asset, webutation_str),
                        "solution": "n/a",
                        "metadata": {"tags": ["domain", "reputation"]},
                        "type": "domain_webutation_info",
                        "raw": {"webutation_info": results['Webutation domain info']},
                        "timestamp": ts
                    })

                    if results['Webutation domain info']['Verdict'] == "safe":
                        nb_vulns['info'] += 1
                        issues.append({
                            "issue_id": len(issues)+1,
                            "severity": "info", "confidence": "certain",
                            "target": {"addr": [asset], "protocol": "domain"},
                            "title": "Webutation for '{}' reveals to be '{}'".format(
                                asset, results['Webutation domain info']['Verdict']),
                            "description": "Webutation for '{}' reveals to be '{}:\n\n{}".format(
                                asset, results['Webutation domain info']['Verdict'], webutation_str),
                            "solution": "n/a",
                            "metadata": {"tags": ["domain", "reputation"]},
                            "type": "domain_webutation_verdict",
                            "raw": {"webutation_info": results['Webutation domain info']},
                            "timestamp": ts
                        })
                    if results['Webutation domain info']['Safety score'] <= 80:
                        nb_vulns['medium'] += 1
                        issues.append({
                            "issue_id": len(issues)+1,
                            "severity": "medium", "confidence": "certain",
                            "target": {"addr": [asset], "protocol": "domain"},
                            "title": "Webutation score for '{}' is set to '{}'".format(
                                asset, results['Webutation domain info']['Safety score']),
                            "description": "Webutation score for '{}' is set to '{}':\n\n{}".format(
                                asset, results['Webutation domain info']['Safety score'], webutation_str),
                            "solution": "n/a",
                            "metadata": {"tags": ["domain", "reputation"]},
                            "type": "domain_webutation_badverdict",
                            "raw": {"webutation_info": results['Webutation domain info']},
                            "timestamp": ts
                        })

                # Recap all
                domain_data = "".join((asset, domain_categories, domain_whois,
                                       domain_siblings_str, resolutions_str,
                                       subdomains_str, detected_url_str,
                                       detected_samples_str, undetected_samples_str,
                                       detected_referrer_samples_str, undetected_referrer_samples_str,
                                       pcaps_str, wot_str, webutation_str))
                domain_hash = detected_samples_hash = hashlib.sha1(str(domain_data).encode('utf-8')).hexdigest()[:6]
                nb_vulns['info'] += 1
                issues.append({
                    "issue_id": len(issues)+1,
                    "severity": "info", "confidence": "certain",
                    "target": {"addr": [asset], "protocol": "domain"},
                    "title": "[Scan Summary] Domain report for '{}' (HASH: {})".format(asset, domain_hash),
                    "description": "Domain Report for '{}':\n\n{}\n\nCategories: \n{}\n\nWhois: \n{}\n\nSibling domains: \n{}\n\nResolutions: \n{}\n\nDetected samples: \n{}\n\nUndetected samples: \n{}\n\nDetected referrer samples: \n{}\n\nUndetected referrer samples: \n{}\n\nPcaps: \n{}\n\nWeb-Of-Trust (WOT) info: \n{}\n\nWebutation: \n{}".format(
                        asset, domain_categories, domain_whois, domain_siblings_str,
                        resolutions_str, subdomains_str, detected_url_str,
                        detected_samples_str, undetected_samples_str,
                        detected_referrer_samples_str, undetected_referrer_samples_str,
                        pcaps_str, wot_str, webutation_str),
                    "solution": "n/a",
                    "metadata": {"tags": ["domain"]},
                    "type": "domain_report",
                    "raw": results,
                    "timestamp": ts
                })


        # URL SCAN
        asset_findings = engine.scans[scan_id]["findings"][asset]
        if "scan_url" in asset_findings and "results" in asset_findings["scan_url"]:
            results = asset_findings["scan_url"]["results"]
            if results["response_code"] != 1:
                nb_vulns["info"] += 1
                issues.append({
                    "issue_id": len(issues)+1,
                    "severity": "info", "confidence": "certain",
                    "target": {"addr": [asset], "protocol": "url"},
                    "title": "URL '{}' not found in VT records".format(asset),
                    "description": "URL '{}' not found in VT records".format(asset),
                    "solution": "n/a",
                    "metadata": {"tags": ["url"]},
                    "type": "vt_url_report",
                    "raw": results,
                    "timestamp": ts
                })
            else:
                url_str = "Score: {}/{}\n".format(results['positives'],results['total'])
                url_str = url_str + "Permalink: "+results['permalink']+"\n"
                url_str = url_str + "Scan ID: "+results['scan_id']+"\n"
                url_str = url_str + "Scan Date: "+results['scan_date']+"\n"
                url_str = url_str + "Status: "+results['verbose_msg']+"\n"
                for scan in sorted(results['scans'].keys()):
                    line = "{}: detected={}, result={}".format(
                        scan, results['scans'][scan]['detected'], results['scans'][scan]['result'])
                    if 'detail' in results['scans'].keys():
                        line = line + " ({})\n".format(results['scans']['detail'])
                    url_str = "".join((url_str, line+"\n"))

                url_hash = hashlib.sha1(str(url_str).encode('utf-8')).hexdigest()[:6]
                nb_vulns['info'] += 1
                issues.append({
                    "issue_id": len(issues)+1,
                    "severity": "info", "confidence": "certain",
                    "target": {"addr": [asset], "protocol": "url"},
                    "title": "[Scan Summary] URL report for '{}' (Score: {}/{}, HASH: {})".format(
                        asset, results['positives'], results['total'], url_hash),
                    "description": "URL report for '{}' ({}/{}):\n\n{}".format(
                        asset, results['positives'], results['total'], url_str),
                    "solution": "n/a",
                    "metadata": {"tags": ["url"]},
                    "type": "vt_url_report",
                    "raw": results,
                    "timestamp": ts
                })

                if results['positives'] > 0:
                    nb_vulns['high'] += 1
                    issues.append({
                        "issue_id": len(issues)+1,
                        "severity": "high", "confidence": "certain",
                        "target": {"addr": [asset], "protocol": "url"},
                        "title": "URL scan for '{}' detected at least 1 positive match (Score: {}/{}, HASH: {})".format(
                            asset, results['positives'], results['total'], url_hash),
                        "description": "URL report for '{}' stated at least 1 positive match ({}/{}):\n\n{}".format(
                            asset, results['positives'], results['total'], url_str),
                        "solution": "n/a",
                        "metadata": {"tags": ["url"]},
                        "type": "vt_url_positivematch",
                        "raw": results,
                        "timestamp": ts
                    })

    summary = {
        "nb_issues": len(issues),
        "nb_info": nb_vulns["info"],
        "nb_low": nb_vulns["low"],
        "nb_medium": nb_vulns["medium"],
        "nb_high": nb_vulns["high"],
        "engine_name": "virustotal",
        "engine_version": engine.scanner["version"]
    }

    return issues, summary


@app.route('/engines/virustotal/getfindings/<scan_id>')
def getfindings(scan_id):
    res = {    "page": "getfindings", "scan_id": scan_id}

    # check if the scan_id exists
    if scan_id not in engine.scans.keys():
        res.update({"status": "error", "reason": "scan_id '{}' not found".format(scan_id)})
        return jsonify(res)

    # check if the scan is finished
    status()
    if engine.scans[scan_id]['status'] != "FINISHED":
        res.update({"status": "error", "reason": "scan_id '{}' not finished (status={})".format(scan_id, engine.scans[scan_id]['status'])})
        return jsonify(res)

    issues, summary = _parse_results(scan_id)

    scan = {
        "scan_id": scan_id,
        "assets": engine.scans[scan_id]['assets'],
        "options": engine.scans[scan_id]['options'],
        "status": engine.scans[scan_id]['status'],
        "started_at": engine.scans[scan_id]['started_at'],
        "finished_at": engine.scans[scan_id]['finished_at']
    }

    # Store the findings in a file
    with open(APP_BASE_DIR+"/results/virustotal_"+scan_id+".json", 'w') as report_file:
        json.dump({
            "scan": scan,
            "summary": summary,
            "issues": issues
        }, report_file, default=_json_serial)

    # remove the scan from the active scan list
    clean_scan(scan_id)

    res.update({
        "scan": scan,
        "summary": summary,
        "issues": issues,
        "status": "success"
    })
    return jsonify(res)


@app.before_first_request
def main():
    """First function called."""
    if not os.path.exists(APP_BASE_DIR+"/results"):
        os.makedirs(APP_BASE_DIR+"/results")
    _loadconfig()


if __name__ == '__main__':
    engine.run_app(app_debug=APP_DEBUG, app_host=APP_HOST, app_port=APP_PORT)
