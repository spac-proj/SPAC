#include "nb_timer.h"
#include "nb-timer-manager.h"
#include <stdlib.h>
#include "nb_runtime.h"

nb__timer* nb__alloc_timer(void) {
	if (tls_timer_manager != nullptr) {
		return tls_timer_manager -> Alloc();
	}
	return nullptr;
}
void nb__return_timer(nb__timer* t) {
	if (t != nullptr) {
		tls_timer_manager -> Return(t);
	}
}
void nb__insert_timer(nb__timer* t, unsigned long long to, nb__timer_callback_t cb, void* argument) {
	if (tls_timer_manager != nullptr) {
		tls_timer_manager -> Insert(t, to, cb, argument);
		return;
	}
}
void nb__remove_timer(nb__timer* t) {
	if (tls_timer_manager != nullptr) {
		tls_timer_manager -> Remove(t);
	}
}

extern unsigned long long nb__get_time_ms_now(void);
void nb__init_timers(void) {
	if (tls_timer_manager != nullptr) {
		tls_timer_manager -> Init();
	}
}