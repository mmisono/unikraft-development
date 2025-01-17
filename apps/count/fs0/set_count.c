#include "unicall_wrapper.h"

extern int count;

int atoi(char *str)
{
	int a = 0;
	char *p = str;
	while (*p != '\0' && *p >= '0' && *p <= '9') {
		a *= 10;
		a += (*p - '0');
		p++;
	}
	return a;
}

__attribute__((section(".text")))
int main(int argc, char *argv[])
{
	int c = 0;
	if (argc >= 2) {
		c = atoi(argv[1]);
	}
	// count = c;
	unikraft_write_var(count, c);
	return 0;
}
