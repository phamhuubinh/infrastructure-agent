package io.orion.desktop;

import android.app.Activity;
import android.content.Intent;
import androidx.activity.result.ActivityResult;
import app.tauri.annotation.ActivityCallback;
import app.tauri.annotation.Command;
import app.tauri.annotation.TauriPlugin;
import app.tauri.plugin.Invoke;
import app.tauri.plugin.JSObject;
import app.tauri.plugin.Plugin;
import com.google.zxing.client.android.Intents;
import com.journeyapps.barcodescanner.ScanOptions;
import org.json.JSONObject;

@TauriPlugin
public final class OrionQrPlugin extends Plugin {
    private final Activity activity;
    private boolean scanning;

    public OrionQrPlugin(Activity activity) {
        super(activity);
        this.activity = activity;
    }

    @Command
    public void scan(Invoke invoke) {
        activity.runOnUiThread(() -> {
            if (scanning) {
                invoke.reject("Orion QR scanner is already open");
                return;
            }
            ScanOptions options = new ScanOptions()
                .setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                .setPrompt("Quét QR kết nối Orion")
                .setBeepEnabled(false);
            scanning = true;
            try {
                startActivityForResult(invoke, options.createScanIntent(activity), "onScanResult");
            } catch (RuntimeException error) {
                scanning = false;
                invoke.reject("Orion QR scanner could not open");
            }
        });
    }

    @ActivityCallback
    public void onScanResult(Invoke invoke, ActivityResult result) {
        scanning = false;
        Intent data = result.getData();
        if (data != null && data.getBooleanExtra(Intents.Scan.MISSING_CAMERA_PERMISSION, false)) {
            invoke.reject("Orion QR scanner needs camera permission");
            return;
        }
        JSObject response = new JSObject();
        if (result.getResultCode() != Activity.RESULT_OK) {
            response.put("value", JSONObject.NULL);
        } else {
            String value = data == null ? null : data.getStringExtra(Intents.Scan.RESULT);
            if (value == null || value.length() > 2048) {
                invoke.reject("Invalid Orion QR scan");
                return;
            }
            response.put("value", value);
        }
        invoke.resolve(response);
    }
}
