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
        icon: '/favicon.ico',
        tag: 'evebargain-alert',
      });
    }

    // Sound notification
    if (!audioRef.current) {
      audioRef.current = new Audio('/notification.mp3');
      audioRef.current.volume = 0.5;
    }
    audioRef.current.play().catch(() => {
      // Audio play may be blocked by browser until user interaction
    });
  }, []);

  return { requestPermission, notify };
}
