package com.tanmayhatkar.overwatch;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        // Tier-2 ring escalation (ADR-0019). Must be registered before
        // super.onCreate() per Capacitor's custom-plugin registration contract.
        registerPlugin(RingAlarmPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
