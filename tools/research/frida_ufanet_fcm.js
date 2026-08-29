'use strict';

/*
 * Local Frida tracer for the official Android client 4.0.14 push reverse engineering.
 *
 * Static analysis of version 4.0.14 (419, UfanetGoogle) identified the exact
 * application classes below, so the tracer prefers app-specific hooks and
 * keeps generic Firebase hooks as a fallback.
 *
 * Security:
 *   - Authorization/JWT and provider tokens are never printed.
 *   - SIP credentials and account/device/location identifiers are redacted.
 *   - Notification title/body text is redacted by default.
 *   - Keep captured logs local; do not commit account-specific output.
 */

Java.perform(function () {
    var ActivityThread = Java.use('android.app.ActivityThread');
    var appPackage = String(ActivityThread.currentPackageName());
    if (!appPackage || appPackage === 'null') {
        throw new Error('Could not determine the current Android package name');
    }
    var lastPackageSeparator = appPackage.lastIndexOf('.');
    if (lastPackageSeparator <= 0) {
        throw new Error('Unexpected Android package name: ' + appPackage);
    }
    var vendorPackage = appPackage.substring(0, lastPackageSeparator);

    function out(message) {
        console.log('[UFANET-FCM] ' + message);
    }

    var exactSensitiveKeys = {
        'username': true,
        'password': true,
        'contract': true,
        'flat': true,
        'device_id': true,
        'server': true,
        'skud_id': true,
        'house_id': true,
        'camera_number': true,
        'key_id': true
    };

    function isSensitiveKey(key) {
        var k = String(key || '').toLowerCase();
        return exactSensitiveKeys[k] === true ||
            k.indexOf('token') !== -1 ||
            k.indexOf('auth') !== -1 ||
            k.indexOf('password') !== -1 ||
            k.indexOf('secret') !== -1;
    }

    function safeValue(key, value) {
        var k = String(key || '').toLowerCase();
        if (value === null || value === undefined) {
            return 'null';
        }
        var text = String(value);
        if (isSensitiveKey(k)) {
            return '<redacted len=' + text.length + '>';
        }
        if (k === 'title' || k === 'body' || k === 'message') {
            return '<redacted text len=' + text.length + '>';
        }
        if (text.length > 2000) {
            return text.substring(0, 2000) + '...<truncated>';
        }
        return text;
    }

    function dumpMap(map, label) {
        if (!map) {
            out(label + ': <null>');
            return;
        }
        try {
            var entries = map.entrySet().toArray();
            out(label + ' (' + entries.length + ' keys):');
            for (var i = 0; i < entries.length; i++) {
                var entry = entries[i];
                var key = String(entry.getKey());
                out('  ' + key + ' = ' + safeValue(key, entry.getValue()));
            }
        } catch (e) {
            out(label + ' dump failed: ' + e);
        }
    }

    function dumpBundle(bundle, label) {
        if (!bundle) {
            out(label + ': <no extras>');
            return;
        }
        try {
            var keys = bundle.keySet().toArray();
            out(label + ' (' + keys.length + ' keys):');
            for (var i = 0; i < keys.length; i++) {
                var key = String(keys[i]);
                out('  ' + key + ' = ' + safeValue(key, bundle.get(key)));
            }
        } catch (e) {
            out(label + ' dump failed: ' + e);
        }
    }

    // ------------------------------------------------------------------
    // Exact registration path from 4.0.14:
    // UserManager -> authmodule.Network.NetworkHelper.registerDevice(...)
    // ------------------------------------------------------------------
    try {
        var NetworkHelper = Java.use(
            vendorPackage + '.authmodule.Network.NetworkHelper'
        );
        var registerDevice = NetworkHelper.registerDevice.overload(
            'java.lang.String', // Ufanet JWT
            'java.lang.String', // FCM/HMS token
            'java.lang.String', // generated device UUID
            'java.lang.String', // device title
            'java.lang.String', // package name
            'boolean'           // HMS flag
        );

        registerDevice.implementation = function (
            jwt,
            providerToken,
            deviceUid,
            deviceName,
            packageName,
            isHuawei
        ) {
            out('NetworkHelper.registerDevice(...)');
            out('  auth = <redacted>');
            out('  provider_token = <redacted len=' +
                (providerToken ? String(providerToken).length : 0) + '>');
            out('  device_id = ' + safeValue('device_id', deviceUid));
            out('  title = ' + safeValue('title', deviceName));
            out('  application = ' + String(packageName));
            out('  os = 0');
            out('  token_type = ' + (isHuawei ? '2 (HMS)' : '0 (FCM)'));
            return registerDevice.call(
                this,
                jwt,
                providerToken,
                deviceUid,
                deviceName,
                packageName,
                isHuawei
            );
        };

        var unregisterDevice = NetworkHelper.unregisterDevice.overload(
            'java.lang.String',
            'java.lang.String'
        );
        unregisterDevice.implementation = function (jwt, deviceUid) {
            out('NetworkHelper.unregisterDevice(...)');
            out('  auth = <redacted>');
            out('  device_id = ' + safeValue('device_id', deviceUid));
            return unregisterDevice.call(this, jwt, deviceUid);
        };

        out('hooked app NetworkHelper register/unregister');
    } catch (e) {
        out('app NetworkHelper hooks unavailable: ' + e);
    }

    // ------------------------------------------------------------------
    // Exact Google-flavor receiver from 4.0.14.
    // ------------------------------------------------------------------
    try {
        var FCMService = Java.use(appPackage + '.push.FCMService');

        var appOnNewToken = FCMService.onNewToken.overload('java.lang.String');
        appOnNewToken.implementation = function (token) {
            out('FCMService.onNewToken token=<redacted len=' +
                (token ? String(token).length : 0) + '>');
            return appOnNewToken.call(this, token);
        };

        var appOnMessage = FCMService.onMessageReceived.overload(
            'com.google.firebase.messaging.RemoteMessage'
        );
        appOnMessage.implementation = function (remoteMessage) {
            out('FCMService.onMessageReceived');
            try {
                dumpMap(remoteMessage.getData(), '  RemoteMessage.data');
                var notification = remoteMessage.getNotification();
                if (notification) {
                    out('  RemoteMessage.notification: present');
                    try {
                        out('    title = ' + safeValue('title', notification.getTitle()));
                        out('    body = ' + safeValue('body', notification.getBody()));
                    } catch (e2) {
                        out('    notification metadata read failed: ' + e2);
                    }
                } else {
                    out('  RemoteMessage.notification: null (data-only message)');
                }
            } catch (e3) {
                out('  app RemoteMessage dump failed: ' + e3);
            }
            return appOnMessage.call(this, remoteMessage);
        };

        out('hooked app FCMService onNewToken/onMessageReceived');
    } catch (e) {
        out('app FCMService hooks unavailable: ' + e);
    }

    // Observe the exact map entering the application's central push dispatcher.
    try {
        var PushBase = Java.use(appPackage + '.push.PushBase');
        var processMessage = PushBase.processMessage.overload(
            appPackage + '.push.MessageModel'
        );
        processMessage.implementation = function (messageModel) {
            out('PushBase.processMessage');
            try {
                dumpMap(messageModel.getData(), '  dispatcher data');
            } catch (e2) {
                out('  dispatcher dump failed: ' + e2);
            }
            return processMessage.call(this, messageModel);
        };
        out('hooked PushBase.processMessage');
    } catch (e) {
        out('PushBase.processMessage hook unavailable: ' + e);
    }

    // ------------------------------------------------------------------
    // Generic Firebase fallback. Useful for seeing raw intent extras that may
    // be removed/transformed before application code consumes RemoteMessage.
    // ------------------------------------------------------------------
    try {
        var FirebaseMessagingService = Java.use(
            'com.google.firebase.messaging.FirebaseMessagingService'
        );
        var handleIntent = FirebaseMessagingService.handleIntent.overload(
            'android.content.Intent'
        );
        handleIntent.implementation = function (intent) {
            try {
                out('FirebaseMessagingService.handleIntent action=' +
                    (intent ? String(intent.getAction()) : 'null'));
                if (intent) {
                    dumpBundle(intent.getExtras(), '  Firebase intent extras');
                }
            } catch (e2) {
                out('  handleIntent trace failed: ' + e2);
            }
            return handleIntent.call(this, intent);
        };
        out('hooked generic FirebaseMessagingService.handleIntent');
    } catch (e) {
        out('generic Firebase handleIntent hook unavailable: ' + e);
    }

    // RemoteMessage.getData() fallback; this may produce duplicate output but
    // helps if the app-specific receiver changes in a future build.
    try {
        var RemoteMessage = Java.use('com.google.firebase.messaging.RemoteMessage');
        var getData = RemoteMessage.getData.overload();
        getData.implementation = function () {
            var data = getData.call(this);
            dumpMap(data, 'RemoteMessage.getData fallback');
            return data;
        };
        out('hooked RemoteMessage.getData fallback');
    } catch (e) {
        out('RemoteMessage.getData fallback hook unavailable: ' + e);
    }

    out('tracer ready for ' + appPackage + ' 4.0.14');
});
