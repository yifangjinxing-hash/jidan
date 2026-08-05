package org.jidan.demo;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

public final class MainActivity extends Activity {
    private int count = 0;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER_HORIZONTAL);
        root.setPadding(dp(28), dp(64), dp(28), dp(28));
        root.setBackgroundColor(Color.rgb(9, 13, 10));

        TextView badge = text("ANDROID GUEST · REAL APK", 12, Color.rgb(185, 255, 87));
        badge.setTypeface(Typeface.MONOSPACE, Typeface.BOLD);
        root.addView(badge);

        TextView title = text("Jidan system slot", 30, Color.WHITE);
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        LinearLayout.LayoutParams titleParams = new LinearLayout.LayoutParams(-2, -2);
        titleParams.setMargins(0, dp(24), 0, dp(12));
        root.addView(title, titleParams);

        TextView description = text("This APK is running inside the connected Android virtual device. The wall is now an adapter.", 16, Color.rgb(177, 187, 179));
        description.setGravity(Gravity.CENTER);
        description.setLineSpacing(0, 1.25f);
        root.addView(description, new LinearLayout.LayoutParams(-1, -2));

        final TextView counter = text("Guest events: 0", 17, Color.rgb(185, 255, 87));
        LinearLayout.LayoutParams counterParams = new LinearLayout.LayoutParams(-2, -2);
        counterParams.setMargins(0, dp(45), 0, dp(16));
        root.addView(counter, counterParams);

        Button button = new Button(this);
        button.setText("Execute in Android guest");
        button.setTextSize(15);
        button.setAllCaps(false);
        button.setTextColor(Color.rgb(8, 14, 7));
        button.setBackgroundColor(Color.rgb(185, 255, 87));
        button.setPadding(dp(24), dp(12), dp(24), dp(12));
        button.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View view) {
                count += 1;
                counter.setText("Guest events: " + count);
            }
        });
        root.addView(button, new LinearLayout.LayoutParams(-1, -2));

        TextView proof = text("org.jidan.demo · API 26–37 · no network permission", 11, Color.rgb(102, 113, 104));
        proof.setTypeface(Typeface.MONOSPACE);
        LinearLayout.LayoutParams proofParams = new LinearLayout.LayoutParams(-2, -2);
        proofParams.setMargins(0, dp(28), 0, 0);
        root.addView(proof, proofParams);
        setContentView(root);
    }

    private TextView text(String value, int size, int color) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(size);
        view.setTextColor(color);
        return view;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
