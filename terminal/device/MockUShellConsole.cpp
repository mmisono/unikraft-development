#include <sys/socket.h>
#include <sys/un.h>

#include <unistd.h>
#include <iostream>
#include <sstream>

#include "MockUShellConsole.h"
#include "parameters.h"

ssize_t writeByteByBytes(int fd, const char *buffer, size_t size)
{
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

static bool promptOn = false;

[[noreturn]] void MockUShellConsole::start(const std::string &path)
{
	// cleanup socket if exists
	unlink(path.c_str());

	// create socket
	sockaddr_un address{};
	address.sun_family = AF_UNIX;
	strcpy(address.sun_path, path.c_str());

	int socketFd = socket(AF_UNIX, SOCK_STREAM, 0);
	if (bind(socketFd, (sockaddr *)(&address), sizeof(address)) != 0) {
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
			if (command.find(MOUNT_INFO_COMMAND) == 0) {
				std::string mockedResponse =
				    MOUNT_INFO_RESPONSE_PREFIX "=.:/\n";
				writeByteByBytes(clientFd,
						 mockedResponse.c_str(),
						 mockedResponse.size());
			} else if (command.find("ls") == 0) {
				for (int index = 0; index < 10; index++) {
					std::stringstream mockedResponse;
					mockedResponse << "test_file" << index
						       << "\n";

					std::string renderedResponse =
					    mockedResponse.str();
					writeByteByBytes(
					    clientFd, renderedResponse.c_str(),
					    renderedResponse.size());
				}
			} else if (command.find("ushell-prompt on") == 0) {
				promptOn = true;
			} else if (command.find("ushell-prompt off") == 0) {
				promptOn = false;
			} else {
				std::string mockedResponse =
				    "Mocked response for: " + command + "\n";
				writeByteByBytes(clientFd,
						 mockedResponse.c_str(),
						 mockedResponse.size());
			}

			if(promptOn) {
				writeByteByBytes(clientFd, "> ", 2);
			}
		}
	}
}
