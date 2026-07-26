import { useCallback, useRef } from 'react';

export function useNotifications() {
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const requestPermission = useCallback(async () => {
    if ('Notification' in window && Notification.permission === 'default') {
      await Notification.requestPermission();
    }
  }, []);

  const notify = useCallback((title: string, body: string) => {
    // Browser notification
    if ('Notification' in window && Notification.permission === 'granted') {
      new Notification(title, {
        body,
        icon: '/notification-icon.png',
        tag: 'evebargain-alert',
      });
    }

    // Sound notification. WAV rather than MP3 so the file can be generated
    // without shipping an encoder -- every current browser decodes it.
    if (!audioRef.current) {
      audioRef.current = new Audio('/notification.wav');
      audioRef.current.volume = 0.5;
    }
    // Rewind so back-to-back alerts re-trigger instead of being ignored while
    // the previous play is still in progress.
    audioRef.current.currentTime = 0;
    audioRef.current.play().catch(() => {
      // Autoplay stays blocked until the user has interacted with the page.
    });
  }, []);

  return { requestPermission, notify };
}
