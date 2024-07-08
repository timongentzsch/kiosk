docker run -e DISPLAY=':0' --privileged --network host -v /dev:/dev -v /mnt:/mnt -v /tmp/.X11-unix:/tmp/.X11-unix --rm  -v /home/aegis/assets/:/app/assets/ kiosk

