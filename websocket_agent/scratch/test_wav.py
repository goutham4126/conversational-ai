import wave
import os

def save_wav(pcm_data, filename, sample_rate):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with wave.open(filename, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2) # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    print(f"Saved {filename}")

# Test with dummy data
save_wav(b'\x00\x00' * 16000, 'static/test_user.wav', 16000)
save_wav(b'\x00\x00' * 24000, 'static/test_assistant.wav', 24000)
