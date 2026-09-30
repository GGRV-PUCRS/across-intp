# V2 hybrid IntP -- procfs/perf_event_open/resctrl backends
# C99, glibc, no external libraries beyond libc + libpthread.

CC      ?= gcc
CSTD    ?= -std=c99
WARN     = -Wall -Wextra -Wpedantic -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Werror
OPT     ?= -O2
CFLAGS  ?= $(CSTD) $(WARN) $(OPT) -D_GNU_SOURCE -Iinclude -Isrc
LDFLAGS ?=
LDLIBS   = -lpthread -lm

TARGET   = intp-c-abi-cgroup

SRCS = \
	intp-hybrid.c \
	src/detect.c \
	src/resctrl.c \
	src/perfev.c \
	src/procutil.c \
	src/backend_registry.c \
	src/cpu.c \
	src/netp.c \
	src/nets.c \
	src/blk.c \
	src/mbw.c \
	src/llcmr.c \
	src/llcocc.c \
	src/portable.c

OBJS = $(SRCS:.c=.o)

TEST_SRCS = tests/test-detect.c tests/test-procutil.c \
            tests/test-backend-registry.c tests/test-target.c
TEST_BINS = $(TEST_SRCS:.c=)

.PHONY: all clean tests run-tests integration-tests deb help

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(CFLAGS) -o $@ $(OBJS) $(LDFLAGS) $(LDLIBS)

%.o: %.c
	$(CC) $(CFLAGS) -c -o $@ $<

# Each test binary links the procutil/detect objects it exercises.
TEST_DEPS       = src/detect.o src/procutil.o src/resctrl.o
# Tests that exercise the backend registry pull in every metric source.
TEST_DEPS_FULL  = $(TEST_DEPS) src/perfev.o src/backend_registry.o \
                  src/cpu.o src/netp.o src/nets.o src/blk.o \
                  src/mbw.o src/llcmr.o src/llcocc.o src/portable.o

tests: $(TEST_BINS)

tests/test-detect: tests/test-detect.c $(TEST_DEPS)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS) $(LDLIBS)

tests/test-procutil: tests/test-procutil.c $(TEST_DEPS)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS) $(LDLIBS)

tests/test-backend-registry: tests/test-backend-registry.c $(TEST_DEPS_FULL)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS) $(LDLIBS)

tests/test-target: tests/test-target.c $(TEST_DEPS_FULL)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS) $(LDLIBS)

run-tests: tests
	@for t in $(TEST_BINS); do echo "==> $$t"; ./$$t || exit 1; done

# C38 integration tests (T1-T3): live multi-threaded / churning / nested-slice
# targets. T1 and T2 run unprivileged (systemd --user scope); T3 needs root,
# resctrl and stress-ng and is skipped otherwise. INTP_OLD_BIN / INTP_V33_BIN
# enable the regression and v3.3-agreement checks (see each script's header).
MT_SPIN = tests/helpers/mt_spin

$(MT_SPIN): tests/helpers/mt_spin.c
	$(CC) -O2 -Wall -Wextra -o $@ $< -lpthread

integration-tests: $(TARGET) $(MT_SPIN)
	tests/t1-multithreaded-target.sh
	tests/t2-thread-churn.sh
	@if [ "$$(id -u)" = 0 ] && [ -d /sys/fs/resctrl/info/L3_MON ]; then \
		tests/t3-nested-slice.sh; \
	else echo "==> T3 skipped (needs root + resctrl L3 monitoring)"; fi

deb: $(TARGET)
	@scripts/build-deb.sh

clean:
	rm -f $(TARGET) $(OBJS) $(TEST_BINS) $(MT_SPIN)

help:
	@echo "Targets:"
	@echo "  all           build $(TARGET) (default)"
	@echo "  tests         build unit tests"
	@echo "  run-tests     build and execute unit tests"
	@echo "  integration-tests  C38 T1-T3 live-target tests (T3: root + resctrl)"
	@echo "  deb           build Debian package via scripts/build-deb.sh"
	@echo "  clean         remove build artifacts"
