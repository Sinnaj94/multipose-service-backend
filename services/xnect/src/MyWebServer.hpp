#pragma once
#include "mongoose.h"

namespace Common
{
    class MyWebServer {
    protected:
        struct mg_context * m_Ctx;
        bool m_ServerState;
        bool m_isInitialized;
        std::string m_BroadcastPorts;
        std::string m_ServerRoot;
        struct mg_callbacks m_Callbacks;
        static struct mg_connection * m_WSConnection;
    public:
        //! Ready handler
        static void ReadyHandler(struct mg_connection * conn)
        {
            std::cout << "[ INFO ]: " << "Client handshake is complete. Ready for data transmission." << std::endl;
        };

        static void ev_handler(struct mg_connection *nc, int ev, void *ev_data) {

        }


        void Initialize(void)
        {
            m_ServerState = false; // Is down initially
            m_isInitialized = false;

            memset(&m_Callbacks, 0, sizeof(m_Callbacks));
            m_Callbacks.upload = MyWebServer::UploadHandler;
            m_Callbacks.websocket_ready = MyWebServer::ReadyHandler;

            m_isInitialized = true;
        }

        static void UploadHandler(struct mg_connection *, const char *file_name)
        {
            std::cout << "Uploaded " << file_name << std::endl;
        }

        void StartServer(const std::string Port = "", const std::string Root = "")
        {
            m_BroadcastPorts = Port;
            m_ServerRoot = Root;
            if (m_BroadcastPorts.empty() == true)
                m_BroadcastPorts = "8080"; // Default to 8080
            if (m_ServerRoot.empty() == true)
                m_ServerRoot = "."; // Default to pwd

            std::cout << "[ INFO ]: " << "Starting data server on port " << m_BroadcastPorts << " and root directory " << m_ServerRoot << " ." << std::endl;

            const char * options[] =
            {
                "listening_ports", m_BroadcastPorts.c_str(),
                "document_root", m_ServerRoot.c_str(),
                NULL
            };

            m_Ctx = mg_start(&m_Callbacks, NULL, options);
            m_ServerState = true;

            std::cout << "[ INFO ]: " << "Done starting server.";
        }
    };
}