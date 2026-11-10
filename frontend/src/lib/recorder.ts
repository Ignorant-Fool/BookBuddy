/**
 * 浏览器端录音 → 16kHz 单声道 WAV。
 *
 * 为什么不用 MediaRecorder（webm/opus）：
 * 后端用 librosa / soundfile 做波形与 MFCC 分析，libsndfile 不认 webm 容器。
 * 这里直接用 Web Audio 采集 PCM，再重采样到 16kHz 并编码成 WAV，
 * 前后端都省掉 ffmpeg 依赖，格式也最稳定。
 */

export interface WavRecording {
  stop: () => Promise<Blob>;
  cancel: () => void;
}

interface AudioCtor {
  new (contextOptions?: AudioContextOptions): AudioContext;
}

function getAudioContext(): AudioCtor {
  const Ctor = (window.AudioContext || (window as any).webkitAudioContext) as AudioCtor;
  if (!Ctor) throw new Error('当前浏览器不支持 Web Audio API');
  return Ctor;
}

function getOfflineContext(): typeof OfflineAudioContext {
  const Ctor = (window.OfflineAudioContext || (window as any).webkitOfflineAudioContext) as typeof OfflineAudioContext;
  if (!Ctor) throw new Error('当前浏览器不支持 OfflineAudioContext');
  return Ctor;
}

function mergeChunks(chunks: Float32Array[]): Float32Array {
  const total = chunks.reduce((sum, c) => sum + c.length, 0);
  const merged = new Float32Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }
  return merged;
}

async function resample(data: Float32Array, from: number, to: number): Promise<Float32Array> {
  if (from === to || data.length === 0) return data;
  const length = Math.max(1, Math.round((data.length * to) / from));
  const Offline = getOfflineContext();
  const offline = new Offline(1, length, to);
  const buffer = offline.createBuffer(1, data.length, from);
  // 复制一份，避免 Float32Array<ArrayBufferLike> 与 copyToChannel 的
  // Float32Array<ArrayBuffer> 类型不匹配（TS 5.7+ 的泛型化 TypedArray）
  const copy = new Float32Array(data.length);
  copy.set(data);
  buffer.copyToChannel(copy, 0);
  const source = offline.createBufferSource();
  source.buffer = buffer;
  source.connect(offline.destination);
  source.start(0);
  const rendered = await offline.startRendering();
  return rendered.getChannelData(0);
}

function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const bytesPerSample = 2;
  const buffer = new ArrayBuffer(44 + samples.length * bytesPerSample);
  const view = new DataView(buffer);

  const writeString = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i));
  };

  writeString(0, 'RIFF');
  view.setUint32(4, 36 + samples.length * bytesPerSample, true);
  writeString(8, 'WAVE');
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * bytesPerSample, true);
  view.setUint16(32, bytesPerSample, true);
  view.setUint16(34, 16, true);
  writeString(36, 'data');
  view.setUint32(40, samples.length * bytesPerSample, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i += 1) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += 2;
  }
  return new Blob([view], { type: 'audio/wav' });
}

/** 开始录音，返回 stop()/cancel() 控制句柄。 */
export async function startWavRecording(): Promise<WavRecording> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  const Ctor = getAudioContext();
  const ctx = new Ctor();
  if (ctx.state === 'suspended') await ctx.resume();

  const source = ctx.createMediaStreamSource(stream);
  const processor = ctx.createScriptProcessor(4096, 1, 1);
  const sink = ctx.createGain();
  sink.gain.value = 0; // 静音，避免录到自己的回放

  const chunks: Float32Array[] = [];
  processor.onaudioprocess = (event) => {
    chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
  };

  source.connect(processor);
  processor.connect(sink);
  sink.connect(ctx.destination);

  const cleanup = () => {
    try { processor.disconnect(); } catch { /* ignore */ }
    try { source.disconnect(); } catch { /* ignore */ }
    try { sink.disconnect(); } catch { /* ignore */ }
    stream.getTracks().forEach((track) => track.stop());
  };

  let finished = false;

  return {
    async stop(): Promise<Blob> {
      if (finished) throw new Error('录音已结束');
      finished = true;
      const sourceRate = ctx.sampleRate;
      cleanup();
      try { await ctx.close(); } catch { /* ignore */ }

      const merged = mergeChunks(chunks);
      if (merged.length === 0) throw new Error('没有采集到音频数据');
      const resampled = await resample(merged, sourceRate, 16000);
      return encodeWav(resampled, 16000);
    },
    cancel() {
      if (finished) return;
      finished = true;
      cleanup();
      void ctx.close().catch(() => undefined);
    },
  };
}
