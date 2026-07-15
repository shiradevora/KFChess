import cv2
import numpy as np
from img import Img

PATH_HOVER = "ImageExperiments/images/moveMousePic.png"
PATH_CLICK = "ImageExperiments/images/clickMousePic.png"

mouse_x, mouse_y = 0, 0
click_x, click_y = -1, -1

def mouse_event_handler(event, x, y, flags, param):
    global mouse_x, mouse_y, click_x, click_y
    if event == cv2.EVENT_MOUSEMOVE:
        mouse_x = x
        mouse_y = y
    elif event == cv2.EVENT_LBUTTONDOWN:
        click_x = x
        click_y = y

def run_experiment():
    global mouse_x, mouse_y, click_x, click_y
    try:
        hover_sprite = Img().read(PATH_HOVER)
        click_sprite = Img().read(PATH_CLICK)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return

    hover_h, hover_w = hover_sprite.img.shape[:2]
    click_h, click_w = click_sprite.img.shape[:2]

    window_name = "KFChess Graphics Sandbox"
    cv2.namedWindow(window_name)
    cv2.setMouseCallback(window_name, mouse_event_handler)

    while True:
        bg_np = np.zeros((600, 600, 4), dtype=np.uint8)
        background = Img()
        background.img = bg_np

        background.put_text("Sandbox Mode - Move & Click!", 150, 40, font_size=0.8, color=(255, 255, 255, 255), thickness=2)

        if click_x != -1 and click_y != -1:
            draw_click_x = max(0, min(click_x - click_w // 2, 600 - click_w))
            draw_click_y = max(0, min(click_y - click_h // 2, 600 - click_h))
            click_sprite.draw_on(background, draw_click_x, draw_click_y)
            background.put_text(f"Last Click: ({click_x}, {click_y})", 15, 570, font_size=0.5, color=(0, 0, 255, 255))

        draw_hover_x = max(0, min(mouse_x - hover_w // 2, 600 - hover_w))
        draw_hover_y = max(0, min(mouse_y - hover_h // 2, 600 - hover_h))
        hover_sprite.draw_on(background, draw_hover_x, draw_hover_y)

        background.put_text(f"Mouse: ({mouse_x}, {mouse_y})", 15, 540, font_size=0.5, color=(0, 255, 0, 255))

        cv2.imshow(window_name, background.img)

        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            break
        if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
            break

    cv2.destroyAllWindows()

if __name__ == "__main__":
    run_experiment()