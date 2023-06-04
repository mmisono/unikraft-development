#include "ubpf_helpers.h"

#include <ubpf.h>
#include <stdio.h>

#include "uk_builtin_bpf_helpers.h"

HelperFunctionList *g_bpf_helper_functions = NULL;
HelperFunctionList *g_additional_helpers = NULL;

HelperFunctionEntry *helper_function_entry_constructor(
    const UK_UBPF_INDEX_t index, const char *function_name,
    const void *function_addr, const ebpf_return_type_t ret_type,
    const UK_EBPF_HELPER_ARG_TYPE_NUM_t arg_type_count,
    const ebpf_argument_type_t arg_types[])
{
	HelperFunctionEntry *entry =
	    malloc(sizeof(HelperFunctionEntry)
		   + arg_type_count * sizeof(ebpf_argument_type_t));
	if (entry == NULL) {
		return NULL;
	}

	entry->m_index = index;
	entry->m_function_addr = function_addr;

	entry->m_function_signature.m_function_name =
	    malloc(strlen(function_name) + 1);
	strncpy(entry->m_function_signature.m_function_name, function_name,
		strlen(function_name) + 1);
	entry->m_function_signature.m_return_type = ret_type;
	entry->m_function_signature.m_num_args = arg_type_count;
	for (int i = 0; i < arg_type_count; ++i) {
		entry->m_function_signature.m_arg_types[i] = arg_types[i];
	}

	return entry;
}

void helper_function_entry_destructor(HelperFunctionEntry *entry)
{
	free(entry->m_function_signature.m_function_name);
	free(entry);
}

/**
 * This function initializes the builtin helper function list if it is not
 * ready.
 * @return The helper function list.
 */
HelperFunctionList *init_builtin_bpf_helpers()
{
	if (g_bpf_helper_functions) {
		return g_bpf_helper_functions;
	}

	g_bpf_helper_functions =
	    helper_function_list_init(helper_function_entry_constructor,
				      helper_function_entry_destructor);
	// add builtin helper functions
	// bpf_map_noop
	helper_function_list_emplace_back(g_bpf_helper_functions, 0,
					  "bpf_map_noop", bpf_map_noop,
					  EBPF_RETURN_TYPE_INTEGER, 0, NULL);

	// bpf_map_get
	ebpf_argument_type_t args_bpf_map_get[] = {
	    EBPF_ARGUMENT_TYPE_CONST_SIZE_OR_ZERO,
	    EBPF_ARGUMENT_TYPE_CONST_SIZE_OR_ZERO,
	};
	helper_function_list_emplace_back(
	    g_bpf_helper_functions, 1, "bpf_map_get", bpf_map_get,
	    EBPF_RETURN_TYPE_INTEGER, 2, args_bpf_map_get);

	// bpf_map_put
	ebpf_argument_type_t args_bpf_map_put[] = {
	    EBPF_ARGUMENT_TYPE_CONST_SIZE_OR_ZERO,
	    EBPF_ARGUMENT_TYPE_CONST_SIZE_OR_ZERO,
	    EBPF_ARGUMENT_TYPE_CONST_SIZE_OR_ZERO,
	};
	helper_function_list_emplace_back(
	    g_bpf_helper_functions, 2, "bpf_map_put", bpf_map_put,
	    EBPF_RETURN_TYPE_INTEGER, 3, args_bpf_map_put);

	/*
      REGISTER_HELPER(bpf_map_del);
      REGISTER_HELPER(bpf_get_addr);
      REGISTER_HELPER(bpf_probe_read);
      REGISTER_HELPER(bpf_time_get_ns);
      REGISTER_HELPER(bpf_puts);
	 register_helper(function_index, "bpf_unwind", bpf_unwind);
      ubpf_set_unwind_function_index(vm, function_index);
	 */

	return g_bpf_helper_functions;
}

void additional_helpers_list_add(const char *label, void *function_ptr)
{
	// TODO
	/*if (additional_helpers == NULL) {
		additional_helpers = init_helper_list();
	}

	list_add_elem(additional_helpers, label, function_ptr);*/
}

void additional_helpers_list_del(const char *label)
{
	// TODO
	/*
	if (additional_helpers != NULL) {
		list_remove_elem(additional_helpers, label);
	}
	 */
}

static inline void register_helper(FILE *logfile, struct ubpf_vm *vm,
				   const UK_UBPF_INDEX_t index,
				   const char *function_name,
				   const void *function_ptr)
{
	if (logfile != NULL) {
		fprintf(logfile, " - [%lu]: %s\n", index, function_name);
	}
	ubpf_register(vm, index, function_name, function_ptr);
}

struct ubpf_vm *init_vm(FILE *logfile)
{
	struct ubpf_vm *vm = ubpf_create();
	if (logfile != NULL) {
		fprintf(logfile, "attached BPF helpers:\n");
	}

	HelperFunctionList *builtin_helpers = init_builtin_bpf_helpers();

	for (HelperFunctionEntry *entry = builtin_helpers->m_head;
	     entry != NULL; entry = entry->m_next) {
		register_helper(logfile, vm, entry->m_index,
				entry->m_function_signature.m_function_name,
				entry->m_function_addr);
	}

	/*
	if (helper_list != NULL) {
		for (uint64_t i = 0; i < helper_list->m_Length; ++i) {
			struct LabeledEntry elem = helper_list->m_List[i];
			register_helper(function_index, elem.m_Label,
					elem.m_Value);
			function_index++;
		}
	}

	register_helper(function_index, "bpf_unwind", bpf_unwind);
	ubpf_set_unwind_function_index(vm, function_index);*/
	return vm;
}

void *readfile(const char *path, size_t maxlen, size_t *len)
{
	FILE *file = fopen(path, "r");

	if (file == NULL) {
		fprintf(stderr, "Failed to open %s: %s\n", path,
			strerror(errno));
		return NULL;
	}

	char *data = calloc(maxlen, 1);
	size_t offset = 0;
	size_t rv;
	while ((rv = fread(data + offset, 1, maxlen - offset, file)) > 0) {
		offset += rv;
	}

	if (ferror(file)) {
		fprintf(stderr, "Failed to read %s: %s\n", path,
			strerror(errno));
		fclose(file);
		free(data);
		return NULL;
	}

	if (!feof(file)) {
		fprintf(stderr,
			"Failed to read %s because it is too large (max %u "
			"bytes)\n",
			path, (unsigned)maxlen);
		fclose(file);
		free(data);
		return NULL;
	}

	fclose(file);
	if (len) {
		*len = offset;
	}
	return (void *)data;
}

int bpf_exec(const char *filename, void *args, size_t args_size, int debug,
	     void (*print_fn)(char *str))
{
	FILE *logfile = NULL;
	if (debug != 0) {
		logfile = fopen("bpf_exec.log", "a");
	}

	if (logfile != NULL) {
		fprintf(logfile, "\n# bpf_exec %s", filename);
		if (args != NULL) {
			fprintf(logfile, " %s", (char *)args);
		}
		fprintf(logfile, "\n");
	}

	struct ubpf_vm *vm = init_vm(logfile);
	size_t code_len;
	void *code = readfile(filename, 1024 * 1024, &code_len);
	if (code == NULL) {
		fclose(logfile);
		return 1;
	}
	char *errmsg;
	int rv;
#if defined(UBPF_HAS_ELF_H)
	rv = ubpf_load_elf(vm, code, code_len, &errmsg);
#else
	rv = ubpf_load(vm, code, code_len, &errmsg);
#endif
	free(code);

	if (rv < 0) {
		size_t buf_size = 100 + strlen(errmsg);
		wrap_print_fn(buf_size, ERR("Failed to load code: %s\n"),
			      errmsg);
		if (logfile != NULL) {
			fprintf(logfile, "Failed to load code: %s\n", errmsg);
		}

		free(errmsg);
		ubpf_destroy(vm);
		if (logfile != NULL) {
			fclose(logfile);
		}
		return 1;
	}

	uint64_t ret;
	if (ubpf_exec(vm, args, args_size, &ret) < 0) {
		print_fn(ERR("BPF program execution failed.\n"));
		if (logfile != NULL) {
			fprintf(logfile, "BPF program execution failed.\n");
		}
	} else {
		wrap_print_fn(100, YAY("BPF program returned: %lu\n"), ret);
		if (logfile != NULL) {
			fprintf(logfile, "BPF program returned: %lu\n", ret);
		}
	}
	ubpf_destroy(vm);
	if (logfile != NULL) {
		fclose(logfile);
	}
	return 0;
}


void print_helper_specs(void (*print_fn)(const char *))
{
	HelperFunctionList *list = init_builtin_bpf_helpers();

	char buffer[8];
	for (HelperFunctionEntry *entry = list->m_head; entry != NULL;
	     entry = entry->m_next) {
		print_fn(entry->m_function_signature.m_function_name);
		print_fn("(");
		for (int index = 0;
		     index < entry->m_function_signature.m_num_args; index++) {
			itoa(entry->m_function_signature.m_arg_types[index],
			     buffer, 16);
			print_fn(buffer);
			if (index
			    != entry->m_function_signature.m_num_args - 1) {
				print_fn(",");
			}
		}

		print_fn(")->");
		itoa(entry->m_function_signature.m_return_type, buffer, 16);
		print_fn(buffer);

		if (entry->m_next != NULL) {
			print_fn(";");
		}
	}
}
