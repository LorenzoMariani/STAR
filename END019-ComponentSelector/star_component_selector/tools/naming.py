"""Nome file immagine: Venditore-NomeComponente.png (es. SimeraSense-xScape50.png)."""
import re

VENDOR = {
    "EnduroSat": "EnduroSat", "ISISpace": "ISISpace", "AAC Clyde Space": "AACClydeSpace", "CubeSpace": "CubeSpace",
    "GomSpace": "GomSpace", "Pumpkin": "Pumpkin", "Pumpkin / Maryland Aerospace": "Pumpkin", "NanoAvionics": "NanoAvionics",
    "Satlab": "Satlab", "Blue Canyon Technologies": "BlueCanyon", "NPC Spacemind": "Spacemind",
    "Hyperion Technologies (AAC Hyperion)": "Hyperion", "Alén Space": "AlenSpace", "Innoflight": "Innoflight",
    "Dragonfly Aerospace": "DragonflyAerospace", "Simera Sense": "SimeraSense", "Satlantis": "Satlantis",
}

# nomi brevi espliciti per i casi dove il nome catalogo e' lungo o ambiguo
SHORT = {
    "endurosat-eps-i": "EPS-I", "endurosat-eps-ii": "EPS-II", "endurosat-cubesat-eps": "CubeSatEPS",
    "endurosat-solar-3u": "3USolarPanel", "endurosat-solar-6u": "6USolarPanel",
    "endurosat-solar-3u-deployable-single": "3UDeployableSolarArray-Single", "endurosat-solar-3u-deployable-double": "3UDeployableSolarArray-Double",
    "endurosat-solar-6u-deployable-single": "6UDeployableSolarArray-Single",
    "pumpkin-csk-mb-ppma1": "CubeSatKitMotherboard-PPMA1", "pumpkin-csk-mb-ppma2": "CubeSatKitMotherboard-PPMA2",
    "pumpkin-csk-mb-ppma3": "CubeSatKitMotherboard-PPMA3", "pumpkin-csk-mb-ppmb1": "CubeSatKitMotherboard-PPMB1",
    "pumpkin-csk-mb-ppmd1": "CubeSatKitMotherboard-PPMD1", "pumpkin-csk-mb-ppmd2": "CubeSatKitMotherboard-PPMD2",
    "pumpkin-fm430": "FM430", "pumpkin-linear-eps-11wh": "LinearEPS-11Wh", "pumpkin-linear-eps-22wh": "LinearEPS-22Wh",
    "pumpkin-bm1-40wh": "BatteryModule1-BM1", "pumpkin-mai-100": "MAI-100", "pumpkin-mai-200": "MAI-200",
    "bct-battery-1p8s": "Battery28V-1P8S", "bct-battery-2p8s": "Battery28V-2P8S",
    "gomspace-nanopower-p60": "NanoPowerP60", "gomspace-nanopower-p80": "NanoPowerP80",
    "gomspace-bpx-100wh-16v": "NanoPowerBPX-16V", "gomspace-bpx-100wh-32v": "NanoPowerBPX-32V", "gomspace-bp8-100wh": "NanoPowerBP8",
    "gomspace-dsp-135-mk2": "NanoPowerDSP-135degMK2", "gomspace-nanostruct-6u": "Nanostruct6U",
    "gomspace-nanocam-c1u-8mm": "NanoCamC1U-8mm", "gomspace-nanocam-c1u-35mm": "NanoCamC1U-35mm", "gomspace-nanocam-c1u-70mm": "NanoCamC1U-70mm",
    "nanoavionics-frame-6u": "StructuralFrame6U", "nanoavionics-satbus-3c2": "SatBus3C2", "nanoavionics-eps-1-0": "EPS1.0", "nanoavionics-eps-2-0": "EPS2.0",
    "nanoavionics-satcom-uhf": "SatCOM-UHF", "satlab-srs-3": "SRS-3", "satlab-srs-4": "SRS-4", "satlab-srx-8": "SRX-8",
    "spacemind-sm03": "SM03", "spacemind-sm06": "SM06", "spacemind-gemini-eps": "GEMINI-EPS", "spacemind-sp3x": "SP3X", "spacemind-sp6x": "SP6X",
    "hyperion-iadcs200": "iADCS200", "hyperion-iadcs400": "iADCS400", "hyperion-im200": "IM200", "alenspace-dara-obc": "DARA-OBC",
    "innoflight-cfc-400-champs": "CFC-400-CHAMPS", "aac-zaphod-3u": "ZAPHOD-3U", "aac-zaphod-6u": "ZAPHOD-6U",
    "aac-photon-side-3u": "PHOTON-SIDE-3U", "aac-starbuck-nano": "STARBUCK-NANO", "aac-starbuck-nano-plus": "STARBUCK-NANO-PLUS",
    "aac-kryten-m3": "KRYTEN-M3", "aac-sirius-obc-leon3ft": "SIRIUS-OBC-LEON3FT", "aac-q7s": "Q7S",
    "aac-pulsar-utrx": "PULSAR-UTRX", "aac-pulsar-vutrx": "PULSAR-VUTRX", "aac-pulsar-stx": "PULSAR-STX", "aac-pulsar-hstx": "PULSAR-HSTX",
    "aac-trx-u": "TRX-U", "aac-quasar-strx": "QUASAR-STRX", "aac-optimus-30": "OPTIMUS-30", "aac-optimus-40": "OPTIMUS-40", "aac-optimus-80": "OPTIMUS-80",
    "satlantis-isim-90": "iSIM-90", "satlantis-isim-90-swir": "iSIM-90-SWIR", "satlantis-isim-170": "iSIM-170", "satlantis-isim-170-swir": "iSIM-170-SWIR",
    "satlantis-graphium": "GRAPHIUM",
    "dragonfly-gecko": "Gecko-RGB", "dragonfly-gecko-wide": "Gecko-WideSwath", "dragonfly-mantis-rgb": "Mantis-RGB", "dragonfly-mantis-ms": "Mantis-MS",
    "dragonfly-mantis-hs": "Mantis-HS", "dragonfly-chameleon-rgb": "Chameleon-RGB", "dragonfly-chameleon-ms": "Chameleon-MS",
    "dragonfly-chameleon-hs": "Chameleon-HS", "dragonfly-caiman-rgb": "Caiman-RGB", "dragonfly-caiman-ms": "Caiman-MS",
    "simera-triscape50": "TriScape50", "simera-multiscape50": "MultiScape50", "simera-hyperscape50": "HyperScape50",
    "simera-triscape100": "TriScape100", "simera-multiscape100": "MultiScape100", "simera-hyperscape100": "HyperScape100",
    "simera-monoscape200": "MonoScape200", "simera-triscape200": "TriScape200", "simera-multiscape200": "MultiScape200",
    "endurosat-structure-3u": "3UStructure", "endurosat-structure-6u": "6UStructure", "isis-structure-3u": "3UStructure", "isis-structure-6u": "6UStructure",
    "isis-solar-3u": "SolarPanel3U", "isis-trxvu": "TRXVU", "endurosat-obc": "OnboardComputer", "endurosat-uhf": "UHFTransceiver",
    "endurosat-sband": "SBandTransceiver", "endurosat-xband": "XBandTransmitter", "endurosat-sband-max": "SBandTransceiverMax",
    "endurosat-xband-sdr": "XBandSDR", "gomspace-nanomind-a3200": "NanoMindA3200", "gomspace-nanocom-ax100": "NanoComAX100",
    "cubespace-cubeadcs-3axis-small": "CubeADCS-3AxisSmall", "cubespace-cubeadcs-ymomentum-small": "CubeADCS-YMomentumSmall",
    "bct-xact-15": "XACT-15", "bct-xact-50": "XACT-50", "bct-xact-100": "XACT-100",
}


def image_name(c):
    vend = VENDOR[c["vendor"]]
    part = SHORT.get(c["id"]) or re.sub(r"[^A-Za-z0-9\-.]", "", re.sub(r"\(.*?\)", "", c["name"]))
    return f"{vend}-{part}.png"
