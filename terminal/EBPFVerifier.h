//
// Created by ken on 22.05.23.
//

#ifndef USHELL_TERMINAL_EBPFVERIFIER_H
#define USHELL_TERMINAL_EBPFVERIFIER_H

#include <string>
#include <vector>
#include <filesystem>
#include "config.hpp"
#include "platform.hpp"

struct eBPFVerifyResult {
    bool ok;
    double took;

};

class EBPFVerifier {
public:
    EBPFVerifier(const std::filesystem::path &symbols, const std::filesystem::path &helperDefinitions,
                 ebpf_verifier_options_t verifierOptions);

    std::vector<std::string> getSections(const std::filesystem::path &bpfFile);

    struct eBPFVerifyResult verify(const std::filesystem::path &bpfFile, const std::string &desiredSection);

private:
    const std::filesystem::path &mSymbols;
    const std::filesystem::path &mHelperDefinitions;
    const ebpf_verifier_options_t mVerifierOptions;

    const ebpf_platform_t *mPlatform;
};


#endif //USHELL_TERMINAL_EBPFVERIFIER_H
