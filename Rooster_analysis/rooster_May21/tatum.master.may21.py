import numpy as np
from scipy.io import wavfile
from scipy.signal import spectrogram
from scipy.signal import find_peaks
from scipy.signal import medfilt
import matplotlib.pyplot as plt
import pandas as pd
import os

wav_path = 'rooster_May21.wav'   # place the WAV in same folder or edit path
if not os.path.exists(wav_path):
    raise SystemExit("WAV not found: " + wav_path)

rate, data = wavfile.read(wav_path)
if data.ndim > 1:
    data = data.mean(axis=1)
data = data.astype(np.float32)
data /= (np.max(np.abs(data)) + 1e-12)

nperseg = 4096
noverlap = nperseg // 2
f, t, Sxx = spectrogram(data, fs=rate, nperseg=nperseg, noverlap=noverlap, scaling='density', mode='magnitude')

mask = (f >= 10) & (f <= 5000)
f_sel = f[mask]
S_sel = Sxx[mask, :]

dom_freq = np.zeros(len(t))

for i in range(len(t)):
    col = S_sel[:, i]
    
    if np.max(col) < 1e-11: 
        dom_freq[i] = 0.0
    else:
        # Tighten the window exactly around the 2-pulse-per-rev bank frequency (600 to 6600 RPM)
        search_mask = (f_sel >= 15) & (f_sel <= 130)
        f_search = f_sel[search_mask]
        col_search = col[search_mask]
        
        # Increase prominence significantly so it only grabs the sharpest, dominant exhaust peak
        peaks, _ = find_peaks(col_search, height=np.max(col_search) * 0.3, prominence=np.max(col_search) * 0.15)
        
        if len(peaks) > 0:
            dom_freq[i] = f_search[peaks[0]]
        else:
            dom_freq[i] = f_search[np.argmax(col_search)]

# Mathematically verified multiplier for an un-merged twin-turbo V8 exhaust bank (4 pulses/rev)
multiplier = 15.0
crank_rpm = dom_freq * multiplier
# Convert to a temporary Pandas Series to use its advanced rolling window feature
rpm_series = pd.Series(crank_rpm)
freq_series = pd.Series(dom_freq)

# Apply a rolling Gaussian window to blend the discrete FFT stair-steps smoothly
# window=7 controls the smoothness; win_type='gaussian' creates a fluid line
crank_rpm_smoothed = rpm_series.rolling(window=7, center=True, win_type='gaussian').mean(std=2).fillna(rpm_series)
dom_freq_smoothed = freq_series.rolling(window=7, center=True, win_type='gaussian').mean(std=2).fillna(freq_series)
out_spec = 'spectrogram.png'
out_spec_rpm = 'spectrogram_with_rpm.png'
out_csv = 'rpm_trace.csv'

# Safe check to see if files are locked before plotting
for file_path in [out_spec, out_spec_rpm, out_csv]:
    if os.path.exists(file_path):
        try:
            # Try opening in append mode to check for write locks
            with open(file_path, 'a'):
                pass
        except PermissionError:
            raise SystemExit(f"CRASH PREVENTION: The file '{file_path}' is currently open in Excel or another program. Please close it and rerun the script.")

plt.figure(figsize=(12,6))
plt.pcolormesh(t, f_sel, 20*np.log10(S_sel + 1e-12), shading='gouraud', cmap='magma')
plt.ylabel("Frequency (Hz)")
plt.xlabel("Time (s)")
plt.title("Spectrogram (0–5000 Hz)")
plt.ylim(10,5000)
plt.xlim(0.6, 20.6)     # <-- Add this line here to crop the time axis
plt.yscale('log')  # <-- Add this line to enable the log scale
plt.colorbar(label='Intensity (dB)')
plt.tight_layout()
plt.savefig(out_spec, dpi=200)
plt.close()

fig, ax1 = plt.subplots(figsize=(12,6))
pcm = ax1.pcolormesh(t, f_sel, 20*np.log10(S_sel + 1e-12), shading='gouraud', cmap='magma')
ax1.set_ylabel("Frequency (Hz)")
ax1.set_xlabel("Time (s)")
ax1.set_ylim(10,5000)
ax1.set_yscale('log')  # <-- Add this line here
ax1.set_xlim(0.6, 20.6)  # <-- Add this line here to crop the time axis

ax1.plot(t, dom_freq_smoothed, color='white', linewidth=1.0, label='Dominant freq (Hz)')

ax2 = ax1.twinx()
ax2.plot(t, crank_rpm_smoothed, color='cyan', linewidth=1.2, alpha=0.8, label='Estimated Crank RPM')
ax2.set_ylabel('Estimated Crank RPM')
ax2.set_ylim(0, np.nanmax(crank_rpm)*1.1 if np.nanmax(crank_rpm)>0 else 7000)

lines = [plt.Line2D([0],[0], color='white', linewidth=1.0),
         plt.Line2D([0],[0], color='cyan', linewidth=1.2)]
labels = ['Dominant freq (Hz)', 'Estimated Crank RPM']
ax1.legend(lines, labels, loc='upper right')

plt.title('Spectrogram (0–5000 Hz) with Estimated Crank RPM Overlay')
plt.tight_layout()
fig.savefig(out_spec_rpm, dpi=200)
plt.close(fig)

# --- PLACE THE CLEANING LINES HERE (Right before the DataFrame) ---
# Create a mask to only keep data from 0.6 to 20.6 seconds
valid_time_mask = (t >= 0.6) & (t <= 20.6)

# Change this section right before saving the CSV:
t_clean = t[valid_time_mask]

# Update these two lines to use the smoothed arrays!
dom_freq_clean = dom_freq_smoothed[valid_time_mask]
crank_rpm_clean = crank_rpm_smoothed[valid_time_mask]

df = pd.DataFrame({
    'time_s': t_clean, 
    'dominant_freq_hz': dom_freq_clean, 
    'estimated_crank_rpm': crank_rpm_clean
})
df.to_csv(out_csv, index=False)

print("Done. Files saved successfully:", out_spec, out_spec_rpm, out_csv)

