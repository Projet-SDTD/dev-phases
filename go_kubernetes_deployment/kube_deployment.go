package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/gocql/gocql"

	appsv1 "k8s.io/api/apps/v1"
	apiv1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	v1 "k8s.io/client-go/kubernetes/typed/apps/v1"
	"k8s.io/client-go/rest"
	//
	// Uncomment to load all auth plugins
	// _ "k8s.io/client-go/plugin/pkg/client/auth"
	//
	// Or uncomment to load specific auth plugins
	// _ "k8s.io/client-go/plugin/pkg/client/auth/azure"
	// _ "k8s.io/client-go/plugin/pkg/client/auth/gcp"
	// _ "k8s.io/client-go/plugin/pkg/client/auth/oidc"
)

type handlers struct {
	KubeConfig       v1.DeploymentInterface
	CassandraSession *gocql.Session
}

type singleLine struct {
	FrameId, FaceId, X, Y, Width, Height, MainEmotion int
	TimestampFrame, Url                               string
}

type returnType struct {
	Results []singleLine
}

func createKubeConfig() v1.DeploymentInterface {
	// creates the in-cluster config
	config, err := rest.InClusterConfig()
	if err != nil {
		panic(err.Error())
	}

	clientset, err := kubernetes.NewForConfig(config)
	if err != nil {
		panic(err)
	}

	deploymentsClient := clientset.AppsV1().Deployments("sdtd")
	return deploymentsClient
}

func connectionCassandra() *gocql.Session {
	cluster := gocql.NewCluster("cassandra")
	cluster.Keyspace = "stream_db"
	cluster.Consistency = gocql.Quorum
	session, err := cluster.CreateSession()
	for err != nil {
		time.Sleep(2 * time.Second)
		cluster := gocql.NewCluster("cassandra")
		cluster.Keyspace = "stream_db"
		cluster.Consistency = gocql.Quorum
		session, err = cluster.CreateSession()
	}
	return session
}

func createDeployment(url, quality, fps, streamerName string, deploymentsClient v1.DeploymentInterface) {
	deployment := &appsv1.Deployment{
		ObjectMeta: metav1.ObjectMeta{
			Name: "phase1-" + streamerName,
			Labels: map[string]string{
				"app": "phase1-" + streamerName,
			},
			Namespace: "sdtd",
		},
		Spec: appsv1.DeploymentSpec{
			Replicas: int32Ptr(1),
			Selector: &metav1.LabelSelector{
				MatchLabels: map[string]string{
					"app": "phase1-" + streamerName,
				},
			},
			Template: apiv1.PodTemplateSpec{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{
						"app": "phase1-" + streamerName,
					},
				},
				Spec: apiv1.PodSpec{
					Containers: []apiv1.Container{
						{
							Name:            "phase1-" + streamerName,
							Image:           "ilisius/phase1",
							ImagePullPolicy: "Always",
							Env: []apiv1.EnvVar{
								{
									Name:  "URL",
									Value: url,
								},
								{
									Name:  "FPS",
									Value: fps,
								},
								{
									Name:  "Stream_QUALITY",
									Value: quality,
								},
								{
									Name:  "KAFKA_URL",
									Value: "kafka-svc:9092",
								},
							},
							Resources: apiv1.ResourceRequirements{
								Limits: apiv1.ResourceList{
									apiv1.ResourceCPU:    resource.MustParse("2"),
									apiv1.ResourceMemory: resource.MustParse("500Mi"),
								},
							},
						},
					},
					RestartPolicy: "Always",
				},
			},
		},
	}

	// Create Deployment
	fmt.Println("Creating deployment...")
	result, err := deploymentsClient.Create(context.TODO(), deployment, metav1.CreateOptions{})
	if err != nil {
		panic(err)
	}
	fmt.Printf("Created deployment %q.\n", result.GetObjectMeta().GetName())
}

func destroyDeployment(streamerName string, deploymentsClient v1.DeploymentInterface) {
	deletePolicy := metav1.DeletePropagationForeground
	if err := deploymentsClient.Delete(context.TODO(), "phase1-"+streamerName, metav1.DeleteOptions{
		PropagationPolicy: &deletePolicy,
	}); err != nil {
		panic(err)
	}
	fmt.Println("Deleted deployment.")
}

func int32Ptr(i int32) *int32 { return &i }

//Web server

func (h *handlers) handleStreamStart(w http.ResponseWriter, r *http.Request) {
	fmt.Printf("got /start request\n")
	r.ParseForm()
	url := r.FormValue("URL")
	quality := r.FormValue("QUALITY")
	fps := r.FormValue("FPS")

	if url == "" {
		url = "https://twitch.tv/ponce"
	}
	if quality == "" {
		quality = "720p60"
	}
	if fps == "" {
		fps = "10"
	}
	splitted := strings.Split(url, "/")
	streamerName := splitted[len(splitted)-1]

	createDeployment(url, quality, fps, streamerName, h.KubeConfig)
	w.Write([]byte("Created"))
}

func (h *handlers) handleStreamStop(w http.ResponseWriter, r *http.Request) {
	fmt.Printf("got /stop request\n")
	r.ParseForm()
	url := r.FormValue("URL")

	//for test purposes only
	if url == "" {
		url = "https://twitch.tv/ponce"
	}
	splitted := strings.Split(url, "/")
	streamerName := splitted[len(splitted)-1]

	destroyDeployment(streamerName, h.KubeConfig)
	w.Write([]byte("Destroyed"))
}

func handlePing(w http.ResponseWriter, r *http.Request) {
	fmt.Printf("got /ping request\n")
	w.Write([]byte("OK"))
}

func (h *handlers) handleDbtt(w http.ResponseWriter, r *http.Request) {
	fmt.Printf("got /dbtt request\n")

	r.ParseForm()
	streamingUrl := r.FormValue("URL")

	w.Header().Set("Content-Type", "application/json")
	rt := new([]singleLine)
	var frameId, faceId, x, y, width, height, mainEmotion int
	var timestampFrame, url string
	var iter *gocql.Iter
	if streamingUrl == "" {
		iter = h.CassandraSession.Query(`SELECT frame_id, face_id, x, y, w, h, main_emotion, timestampFrame, url FROM Stream_DB.frames LIMIT 50`).Iter()
	} else {
		iter = h.CassandraSession.Query(`SELECT frame_id, face_id, x, y, w, h, main_emotion, timestampFrame, url FROM Stream_DB.frames WHERE url = ? LIMIT 1`, streamingUrl).Iter()
	}

	for iter.Scan(&frameId, &faceId, &x, &y, &width, &height, &mainEmotion, &timestampFrame, &url) {
		fmt.Println(frameId)
		sl := singleLine{frameId, faceId, x, y, width, height, mainEmotion, timestampFrame, url}
		*rt = append(*rt, sl)
	}

	fmt.Println(*rt)

	js, err := json.Marshal(*rt)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	w.Write(js)
}

func main() {
	h := handlers{KubeConfig: createKubeConfig(), CassandraSession: connectionCassandra()}

	http.HandleFunc("/start", h.handleStreamStart)
	http.HandleFunc("/stop", h.handleStreamStop)
	http.HandleFunc("/ping", handlePing)
	http.HandleFunc("/dbtt", h.handleDbtt)

	err := http.ListenAndServe(":80", nil)
	if errors.Is(err, http.ErrServerClosed) {
		fmt.Printf("server closed\n")
	} else if err != nil {
		fmt.Printf("error starting server: %s\n", err)
		os.Exit(1)
	}
}
