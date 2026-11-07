/* Synthetic test helper: flush and hold the first virtual pointer press. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>

struct wl_proxy;
struct wl_interface;
extern const char *wl_proxy_get_class(struct wl_proxy *proxy);
extern void *wl_proxy_get_display(struct wl_proxy *proxy);
extern int wl_display_flush(void *display);

struct wl_proxy *wl_proxy_marshal_flags(struct wl_proxy *proxy, uint32_t opcode,
                                      const struct wl_interface *interface,
                                      uint32_t version, uint32_t flags, ...) {
    void *args = __builtin_apply_args();
    static void (*real)(void);
    static int buttons;
    if (!real) real = (void (*)(void))dlsym(RTLD_NEXT, "wl_proxy_marshal_flags");
    int hold = proxy && !strcmp(wl_proxy_get_class(proxy), "zwlr_virtual_pointer_v1") &&
               opcode == 2 && ++buttons == 1;
    void *result = __builtin_apply(real, args, 256);
    if (hold) {
        /* Deliver the press frame before holding; a flush alone is insufficient. */
        typedef struct wl_proxy *(*marshal_fn)(struct wl_proxy *, uint32_t,
                                               const struct wl_interface *, uint32_t,
                                               uint32_t, ...);
        marshal_fn send_frame = (marshal_fn)dlsym(RTLD_NEXT, "wl_proxy_marshal_flags");
        send_frame(proxy, 4, NULL, version, 0);
        wl_display_flush(wl_proxy_get_display(proxy));
        usleep(1500000);
    }
    __builtin_return(result);
}
