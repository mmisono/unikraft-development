#ifndef BPF_HELPERS_H
#define BPF_HELPERS_H

#include <stdint.h>

#define bpf_map_get ((uint64_t(*)(uint64_t key1, uint64_t key2))0)
#define bpf_map_put ((void (*)(uint64_t key1, uint64_t key2, uint64_t value))1)
#define bpf_map_del ((void (*)(uint64_t key1, uint64_t key2))2)

#define bpf_notify ((void (*)(uint64_t function_address))3)
#define bpf_get_ret_addr ((uint64_t(*)(const char *function_name))4)

#endif /* BPF_HELPERS_H */
