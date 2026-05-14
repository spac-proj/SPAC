#include "nb-timer-manager.h"
#include "nb_timer.h"
#include "nb_runtime.h"

namespace ns3 {
  NbTimerManager::NbTimerManager()
    : m_freeList(nullptr), m_timers_head(nullptr) {}

  TypeId
  NbTimerManager::GetTypeId() {
    static TypeId tid = TypeId("ns3::NbTimerManager")
      .SetParent<Object>()
      .SetGroupName("Nb")
      .AddConstructor<NbTimerManager>();
    return tid;
  }

  void NbTimerManager::Init() {
    // Initialize the free list with all timers in the pool
    m_freeList = &m_timerPool[0];
    for (int i = 0; i < MAX_TIMERS - 1; ++i) {
      m_timerPool[i].next = &m_timerPool[i + 1];
    }
    m_timerPool[MAX_TIMERS - 1].next = nullptr;
  }

  nb__timer* NbTimerManager::Alloc() {
    if (m_freeList == nullptr) {
        NS_FATAL_ERROR("No free timers available in the pool");
        return nullptr;
    }
    nb__timer* t = m_freeList;
    m_freeList = m_freeList->next;
    t->next = nullptr; // Clear the next pointer
    return t;
  }

  void NbTimerManager::Return(nb__timer* t) {
    if (t == nullptr) {
        NS_FATAL_ERROR("Cannot return a null timer");
        return;
    }
    t->next = m_freeList; // Add to the front of the free list
    m_freeList = t;
  }

  void NbTimerManager::Insert(nb__timer* t, uint64_t to_ms, nb__timer_callback_t cb, void* arg) {
    if (t == nullptr) {
        NS_FATAL_ERROR("Cannot insert a null timer");
        return;
    }
    t->callback = cb;
    t->argument = arg;
    t->timeout = to_ms;

    int64_t diff = static_cast<int64_t>(to_ms) - static_cast<int64_t>(nb__get_time_ms_now());
    if (diff < 0) {
        diff = 0; // schedule immediately if already overdue
    }
    Time delay = MilliSeconds(diff);
    t->ns3_event_id = Simulator::Schedule(delay, &TimerWrapper, t);
  }
  void NbTimerManager::TimerWrapper(nb__timer* t) {
    uint64_t now = nb__get_time_ms_now();
    if (t->callback) {
        t->callback(t, t->argument, now);
    }
  }

  void NbTimerManager::Remove(nb__timer* t) {
    if (t == nullptr) {
        NS_FATAL_ERROR("Cannot remove a null timer");
        return;
    }
    if (t->ns3_event_id.IsPending()) {
        Simulator::Cancel(t->ns3_event_id);
    }
    t->ns3_event_id = EventId(); // Clear the EventId
    t->timeout = 0; // Reset timeout
  }
}

