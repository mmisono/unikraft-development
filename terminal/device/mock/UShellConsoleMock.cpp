#include <sys/socket.h>
#include <sys/un.h>

#include <unistd.h>
#include <iostream>
#include <sstream>
#include <boost/algorithm/string/trim.hpp>

#include "UShellConsoleMock.hpp"
#include "parameters.h"

ssize_t writeByteByByte(int fd, const char *buffer, size_t size) {
    ssize_t bytesWritten = 0;
    for (size_t i = 0; i < size; i++) {
        ssize_t bytesWrittenNow = write(fd, buffer + i, 1);
        if (bytesWrittenNow < 0) {
            return bytesWrittenNow;
        }
        bytesWritten += bytesWrittenNow;
    }

    return bytesWritten;
}

[[noreturn]] void UShellConsoleMock::start(const std::string &path) {
    // cleanup socket if exists
    unlink(path.c_str());

    // create socket
    sockaddr_un address{};
    address.sun_family = AF_UNIX;
    strcpy(address.sun_path, path.c_str());

    int socketFd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (bind(socketFd, (sockaddr *) (&address), sizeof(address)) != 0) {
        std::cerr << errno << std::endl;
        throw std::runtime_error("Could not bind to socket");
    }

    if (listen(socketFd, 1) != 0) {
        std::cerr << errno << std::endl;
        throw std::runtime_error("Could not listen to socket");
    }

    while (true) {
        int clientFd = accept(socketFd, nullptr, nullptr);

        while (true) {
            char buffer[256];
            ssize_t bytesRead =
                    read(clientFd, buffer, sizeof(buffer));

            std::string command(buffer, bytesRead);
            boost::trim_right(command);

            if (command.find(MOUNT_INFO_COMMAND) == 0) {
                std::string mockedResponse =
                        MOUNT_INFO_RESPONSE_PREFIX "=.:/\n";
                writeByteByByte(clientFd,
                                mockedResponse.c_str(),
                                mockedResponse.size());
            } else if (command.find("ls") == 0) {
                for (int index = 0; index < 10; index++) {
                    std::stringstream mockedResponse;
                    mockedResponse << "test_file" << index
                                   << "\n";

                    std::string renderedResponse =
                            mockedResponse.str();
                    writeByteByByte(
                            clientFd, renderedResponse.c_str(),
                            renderedResponse.size());
                }
            } else if (command.find(BPF_HELPER_INFO_COMMAND) == 0) {
                const char *mockedResponse =
                        BPF_HELPER_FUNCTION_INFO_RESPONSE_PREFIX
                        "="
                        "0,0:bpf_map_noop()->0;"
                        "1,0:bpf_map_get(1,1)->0;"
                        "2,0:bpf_map_put(1,1,1)->0;"
                        "3,0:bpf_map_del(1,1)->0;"
                        "6,0:bpf_time_get_ns()->0;"
                        "7,0:bpf_unwind(1)->2;"
                        "8,0:bpf_puts(9)->0"
                        "\n"
                        BPF_PROG_TYPE_INFO_RESPONSE_PREFIX
                        "="
                        "1,tracer:0,14,0,8,10"
                        "\n";
                writeByteByByte(clientFd, mockedResponse,
                                strlen(mockedResponse));
            } else if (command.find("close") == 0) {
                close(clientFd);
                close(socketFd);
            } else if (command.empty()) {

            } else {
                std::string mockedResponse =
                        "Unknown command: " + command + "\n";
                writeByteByByte(clientFd,
                                mockedResponse.c_str(),
                                mockedResponse.size());
            }

            writeByteByByte(clientFd, "> ", 2);
        }
    }
}