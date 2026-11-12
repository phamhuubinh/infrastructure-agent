package io.orion.desktop;

import android.app.Activity;
import app.tauri.annotation.Command;
import app.tauri.annotation.TauriPlugin;
import app.tauri.plugin.Invoke;
import app.tauri.plugin.JSObject;
import app.tauri.plugin.Plugin;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Arrays;
import org.json.JSONException;
import org.json.JSONObject;

/** Android side of the native credential IPC. */
@TauriPlugin
public final class OrionVaultPlugin extends Plugin {
    private final OrionCredentialVault vault;

    public OrionVaultPlugin(Activity activity) {
        super(activity);
        vault = OrionCredentialVault.forApp(activity);
    }

    @Command
    public void get(Invoke invoke) {
        byte[] value = null;
        try {
            value = vault.get(invoke.getArgs().getString("origin"));
            JSObject result = new JSObject();
            result.put("pair", value == null
                ? JSONObject.NULL
                : new JSONObject(new String(value, StandardCharsets.UTF_8)));
            invoke.resolve(result);
        } catch (IOException | GeneralSecurityException | JSONException | RuntimeException error) {
            invoke.reject("Orion credential vault read failed");
        } finally {
            if (value != null) Arrays.fill(value, (byte) 0);
        }
    }

    @Command
    public void set(Invoke invoke) {
        byte[] value = null;
        try {
            JSObject args = invoke.getArgs();
            String origin = args.getString("origin");
            value = args.getJSONObject("pair").toString().getBytes(StandardCharsets.UTF_8);
            vault.set(origin, value);
            invoke.resolve();
        } catch (IOException | GeneralSecurityException | JSONException | RuntimeException error) {
            invoke.reject("Orion credential vault write failed");
        } finally {
            if (value != null) Arrays.fill(value, (byte) 0);
        }
    }

    @Command
    public void clear(Invoke invoke) {
        try {
            vault.clear(invoke.getArgs().getString("origin"));
            invoke.resolve();
        } catch (IOException | GeneralSecurityException | RuntimeException error) {
            invoke.reject("Orion credential vault removal failed");
        }
    }
}
