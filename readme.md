# ⚙️ Rishabh Calibration Automation
A **Python-based automated testing and calibration suite** developed during my internship at **Rishabh Instruments Pvt. Ltd.**, designed to automate and streamline the **testing, calibration, and verification** processes for Rishabh’s range of **energy meters** using **Modbus TCP/IP**.
---
## 🚀 Overview
Energy meter calibration and testing often involve manual, repetitive, and error-prone procedures. This project provides a **comprehensive automation framework** that enables both **sequential** and **parallel** calibration of energy meters, ensuring accuracy, consistency, and reliability across all test stages.
Key objectives achieved:
- Automate complete calibration workflow across multiple meter types  
- Eliminate manual intervention and reduce human error  
- Maintain traceability through persistent logs and progress tracking  
- Provide operator-friendly interaction using GUI and console fallbacks  
---
## 🧩 Features
- ⚙️ **Sequential & Parallel Calibration** for 3-phase (3P3W, 3P4W) and 4-wire (4WS1, 4WS2) meters  
- 🔌 **Reliable Modbus TCP/IP Communication** with CRC integrity checks  
- 📊 **Parameter Reading**: Voltage, Current, Power, PF, Frequency  
- 🔘 **Key Test Automation** simulating on-meter button inputs  
- 🧾 **Post-Calibration Programming** (Serial number, Model imprint)  
- 🧠 **Persistent Progress Tracking** and JSON-based recovery  
- 🪟 **Tkinter-Based UI Prompts** with CLI fallback  
- 🧪 **Simulation Mode** for testing without hardware  
- 🧰 **Detailed Error Calculation** and result reporting  
---
## 🛠 Tech Stack
- **Language**: Python 3.x  
- **Communication Protocol**: Modbus TCP/IP (ASCII)  
- **UI**: Tkinter  
- **Data Handling**: JSON, Struct  
- **Modules**: socket, threading, time, os, re, struct  
---
## 📂 Project Structure
```
Rishabh-Calibration-Automation/
│
├── calibration.py             → Core sequential calibration runner  
├── 3P3W.py / 3P4W.py          → Grouped calibration for 3-phase meters  
├── 4WS1.py / 4WS2.py          → Parameter reading for 4-wire meters  
├── key_test.py                → Automated on-meter key test procedures  
├── postcal.py                 → Post-calibration programming routines  
├── readparameters.py          → Parameter reading & key test integration  
├── voltage_impulse_error.py   → Error calculation and analysis module  
├── transport.py               → Socket communication abstraction  
├── ui_helpers.py              → Tkinter & console prompt utilities  
├── config.py                  → Central configuration and initialization  
├── steps.py                   → Step definitions for calibration process  
├── registers.py               → Register mappings and command references  
├── logs/                      → Generated calibration logs and reports  
└── README.md                  → Project documentation    
```
## 🧪 Simulation Mode
When hardware isn’t connected, enabling simulation mode allows developers to:  
- Emulate meter responses  
- Validate calibration logic  
- Test data decoding and socket handling safely  
This makes development and debugging smooth without requiring test benches.  
---
## 📈 Outcomes
✅ Reduced manual testing effort by over **70%**  
✅ Improved calibration **accuracy and repeatability**  
✅ Introduced **real-time progress tracking** and **error reporting**  
✅ Enabled **automated recovery** after interruptions  
---
## 🧾 License
This project is intended for **internal and educational use** under Rishabh Instruments’ development guidelines.  
---
## 🙋‍♂️ Author
Made with 💡 and precision by **Sarvesh Ghotekar**  
*Intern, Rishabh Instruments Pvt. Ltd.*  
🔗 [LinkedIn](https://www.linkedin.com/in/sarveshghotekar/) • [Portfolio](https://sarvessh05.github.io/Portfolio/)

