// NbTimerManager.h
#ifndef Nb_TIMER_H
#define Nb_TIMER_H

#include "ns3/event-id.h"
#include "ns3/simulator.h"
#include <cstdint>
#include <functional>

extern "C" {
#include "nb_timer.h"
}

namespace ns3 {
    class NbTimerManager : public Object {
    public:
        static TypeId GetTypeId();
    
        // Constructor
        NbTimerManager();
    
        // Initialize internal timer pool (must be called before use)
        void Init();
    
        // Allocate a timer object from the internal pool
        nb__timer* Alloc();
    
        // Return a used timer back to the pool
        void Return(nb__timer* t);
    
        // Insert a new timer, scheduled at `to_ms` (absolute ms time)
        void Insert(nb__timer* t, uint64_t to_ms, nb__timer_callback_t cb, void* arg);
    
        // Cancel an active timer
        void Remove(nb__timer* t);
    
    private:
        static constexpr int MAX_TIMERS = MAX_TIMER_ALLOCS;
    
        // Internal timer pool used for allocation
        nb__timer m_timerPool[MAX_TIMERS];
    
        // Free list pointer into the pre-allocated timer pool
        nb__timer* m_freeList;

        nb__timer* m_timers_head;
    
        // Static callback wrapper for ns-3 scheduled events
        static void TimerWrapper(nb__timer* t);
    };        
}
#endif // Nb_TIMER_H