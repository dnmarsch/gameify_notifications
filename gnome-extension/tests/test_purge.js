#!/usr/bin/gjs -m
// Unit tests for the extension's pure matching logic. Run: gjs -m test_purge.js
// (also driven by tests/test_gnome_extension.py under pytest).

import System from 'system';
import {matchesNotification, selectMatching}
    from '../gameify-tray-purge@gameify.local/purge.js';

let failures = 0;
function check(cond, msg) {
    if (cond) {
        print(`ok   - ${msg}`);
    } else {
        print(`FAIL - ${msg}`);
        failures++;
    }
}

const A = {title: 'Carol', body: 'teams.cloud.microsoft'};
const B = {title: 'Carol', body: 'outlook.cloud.microsoft'};
const C = {title: 'Dave',  body: 'teams.cloud.microsoft'};

check(matchesNotification(A, 'Carol', 'teams.cloud.microsoft'), 'exact title+body matches');
check(!matchesNotification(A, 'Carol', 'outlook.cloud.microsoft'), 'wrong body -> no match');
check(!matchesNotification(A, 'Dave', 'teams.cloud.microsoft'), 'wrong title -> no match');
check(matchesNotification(A, '', ''), 'empty args are wildcards');
check(matchesNotification(A, 'Carol', ''), 'title-only match');
check(matchesNotification({}, '', ''), 'missing fields tolerated');
check(!matchesNotification({}, 'Carol', ''), 'missing title -> no match for a real summary');

const one = selectMatching([A, B, C], 'Carol', 'teams.cloud.microsoft');
check(one.length === 1 && one[0] === A, 'selectMatching picks only the exact one');
check(selectMatching([A, B, C], '', '').length === 3, 'wildcards select all');
check(selectMatching([A, B, C], 'Nobody', '').length === 0, 'no match -> empty');

if (failures > 0) {
    print(`\n${failures} failure(s)`);
    System.exit(1);
}
print('\nALL PASS');
