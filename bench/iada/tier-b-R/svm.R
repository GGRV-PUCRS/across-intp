#library("stringr")
#source("~/interference/r/simulation/input_dataset.R")
#source("~/interference/r/simulation/kmeans.R")

#training_dataset_folder <- str_replace_all(paste(project_folder_inside,"forced/")," ", "")

total<-input_dataset(training_dataset_folder)

if(firstTime==0){

	modelo_svm <- svm(category ~ ., data = total , type='C-classification',  nu=0.10, scale=TRUE, kernel="polynomial")  
  	save(modelo_svm, file=paste(project_folder_inside, "svm_model.rda", sep = ""))
	fisrtTime=2
	
}
if(firstTime==1){
	load(paste(project_folder_inside, "svm_model.rda", sep = ""))
	firstTime=2
}

classifier_percent<- function(a,b){
  
  df<-data.frame()
  
  interval <- b
  finish <- nrow(a)/interval
  
  for(i in 0:finish) {
    if(i==as.integer(finish)){
      x<-(i*interval)
      y<- nrow(a)
    }else{
      x<-(i*interval)
      y<- ((i*interval+interval)-1)
    }
    
    teste <- predict(modelo_svm, a[x:y,])
    result <- a$category[x:y]
    #print(table(teste, result))
    #message(paste(i+1, " - ",x,y))
    
    tab<-table(teste, result)
    for(h in 1:nrow(tab)){
      row <- data.frame(interval=as.numeric(i), resource=as.factor(rownames(tab)[h]), per=as.integer(((tab[h,1]/(y-x+1))*100)))
      df <- bind_rows(df, row)
    }
    
  }
  return(df)
}

svm_classifier_class<- function(a,b){
  result <- svm_classifier_percent(a,b)
  df=data.frame()
  control<-0
  interval<-0
  
  for( h in 1:nrow(result)){
    #print(result[h,1])
    if(result[h,1]!=interval){
      interval <- interval+1      
      control <- 0
      row <- data.frame(interval=as.numeric(interval*b), resource=as.factor(resource))
      df <- bind_rows(df, row)
      
    }
    if(result[h,3]>control){
      resource<-result[h,2]
      #print(paste(resource, " - ", control))
      control<-result[h,3]
    }
    
    if(h==nrow(result)){
      interval <-  interval+1          
      row <- data.frame(interval=as.numeric(interval*b), resource=as.factor(resource))
      df <- bind_rows(df, row)
    }
    
  }
  
  
  #print(df)
  return(df)
}



svm_classifier_level<- function(a,x,y){
  
  
  df<-data.frame()
  df_cpu<-data.frame()
  df_mem<-data.frame()
  df_disk<-data.frame()
  df_net<-data.frame()
  df_cache<-data.frame()
  df_regime<-data.frame()
  cpu<-""
  mem<-""
  disk<-""
  net<-""
  cache<-""
  regime<-""
  v_cpu<-vector()
  v_mem<-vector()
  v_disk<-vector()
  v_net<-vector()
  v_cache<-vector()
  v_regime<-vector()
  
     for(j in x:y){
      #print(a[j,])
      #print(paste(i,j))
      predict <- predict(modelo_svm, a[j,])
      if(predict=="cpu"){
        df_cpu<-bind_rows(df_cpu, a[j,])
        
      }else if(predict=="mem"){
        df_mem<-bind_rows(df_mem, a[j,])
        
      }else if(predict=="disk"){
        df_disk<-bind_rows(df_disk, a[j,])
        
      }else if(predict=="net"){
        df_net<-bind_rows(df_net, a[j,])
        
      }else if(predict=="cache"){
        df_cache<-bind_rows(df_cache, a[j,])

      }else if(predict=="regime"){
        df_regime<-bind_rows(df_regime, a[j,])

      }
    }
    
    
    if(nrow(df_cpu)>0){
      v_cpu <- c(v_cpu, predict_cpu.kmeans(cl_cpu, df_cpu[,1:15]))
      aa<-data.frame()
      aa<-cbind(c("low","mod","hig"),c(sum(str_count(v_cpu, "low")),sum(str_count(v_cpu, "mod")),sum(str_count(v_cpu, "hig"))))
      #print(aa)
      #print(which.max(aa[,2]))
      if(which.max(aa[,2])==1)
      {
        cpu<-"low"
      }else if(which.max(aa[,2])==2)
      {
        cpu<-"mod"
      }else if(which.max(aa[,2])==3)
      {
        cpu<-"hig"
      }
      
    }else{
      cpu<-"abs"
    }
    if(nrow(df_mem)>0){
      v_mem <- c(v_mem, predict_mem.kmeans(cl_mem, df_mem[,1:15]))
      aa<-data.frame()
      aa<-cbind(c("low","mod","hig"),c(sum(str_count(v_mem, "low")),sum(str_count(v_mem, "mod")),sum(str_count(v_mem, "hig"))))
      #print(aa)
      #print(which.max(aa[,2]))
      if(which.max(aa[,2])==1)
      {
        mem<-"low"
      }else if(which.max(aa[,2])==2)
      {
        mem<-"mod"
      }else if(which.max(aa[,2])==3)
      {
        mem<-"hig"
      }
    }else{
      mem<-"abs"
    }
    if(nrow(df_disk)>0){
      v_disk <- c(v_disk, predict_disk.kmeans(cl_disk, df_disk[,1:15]))
      aa<-data.frame()
      aa<-cbind(c("low","mod","hig"),c(sum(str_count(v_disk, "low")),sum(str_count(v_disk, "mod")),sum(str_count(v_disk, "hig"))))
      #print(aa)
      #print(which.max(aa[,2]))
      if(which.max(aa[,2])==1)
      {
        disk<-"low"
      }else if(which.max(aa[,2])==2)
      {
        disk<-"mod"
      }else if(which.max(aa[,2])==3)
      {
        disk<-"hig"
      }
    }else{
      disk<-"abs"
    }
    if(nrow(df_net)>0){
      v_net <- c(v_net, predict_net.kmeans(cl_net, df_net[,1:15]))
      aa<-data.frame()
      aa<-cbind(c("low","mod","hig"),c(sum(str_count(v_net, "low")),sum(str_count(v_net, "mod")),sum(str_count(v_net, "hig"))))
      #print(aa)
      #print(which.max(aa[,2]))
      if(which.max(aa[,2])==1)
      {
        net<-"low"
      }else if(which.max(aa[,2])==2)
      {
        net<-"mod"
      }else if(which.max(aa[,2])==3)
      {
        net<-"hig"
      }
    }else{
      net<-"abs"
    }
    if(nrow(df_cache)>0){
      v_cache <- c(v_cache, predict_cache.kmeans(cl_cache, df_cache[,1:15]))
      aa<-data.frame()
      aa<-cbind(c("low","mod","hig"),c(sum(str_count(v_cache, "low")),sum(str_count(v_cache, "mod")),sum(str_count(v_cache, "hig"))))
      #print(aa)
      #print(which.max(aa[,2]))
      if(which.max(aa[,2])==1)
      {
        cache<-"low"
      }else if(which.max(aa[,2])==2)
      {
        cache<-"mod"
      }else if(which.max(aa[,2])==3)
      {
        cache<-"hig"
      }
    }else{
      cache<-"abs"
    }
    if(nrow(df_regime)>0){
      v_regime <- c(v_regime, predict_regime.kmeans(cl_regime, df_regime[,1:15]))
      aa<-data.frame()
      aa<-cbind(c("low","mod","hig"),c(sum(str_count(v_regime, "low")),sum(str_count(v_regime, "mod")),sum(str_count(v_regime, "hig"))))
      if(which.max(aa[,2])==1)
      {
        regime<-"low"
      }else if(which.max(aa[,2])==2)
      {
        regime<-"mod"
      }else if(which.max(aa[,2])==3)
      {
        regime<-"hig"
      }
    }else{
      regime<-"abs"
    }

    #print(paste("CPU",cpu))
    #print(paste("MEM",mem))
    #print(paste("DISK",disk))
    #print(paste("NET ",net))
    #print(paste("CACHE",cache))
    row <- data.frame(interval=as.numeric(j), resource="cpu", per=cpu)
    df <- bind_rows(df, row)
    row <- data.frame(interval=as.numeric(j), resource="mem", per=mem)
    df <- bind_rows(df, row)
    row <- data.frame(interval=as.numeric(j), resource="disk", per=disk)
    df <- bind_rows(df, row)
    row <- data.frame(interval=as.numeric(j), resource="net", per=net)
    df <- bind_rows(df, row)
    row <- data.frame(interval=as.numeric(j), resource="cache", per=cache)
    df <- bind_rows(df, row)
    row <- data.frame(interval=as.numeric(j), resource="regime", per=regime)
    df <- bind_rows(df, row)

  
  #print(v_cpu)
  
  return(df)
  
  
}

class_list <- list()

svm_classifier <- function(app_list,interval_list){
  
  for(i in 0:(length(app_list)/7-1)){
    #print(paste("------ ",i," ------"))
    #print(paste("1"," - ", interval_list[[i+1]][1]))
    #print(paste(i*7+1," -- --- ---", i*7+7))
    #svm_classifier_level(as.data.frame(app_list[as.numeric(i*7+1):as.numeric(i*7+7)]), 1, interval_list[[i+1]][1])
    class_list <- c(class_list, svm_classifier_level(as.data.frame(app_list[as.numeric(i*7+1):as.numeric(i*7+7)]), 1, interval_list[[i+1]][1]))
    for(n in 1:(length(interval_list[[i+1]])-1)){
      class_list <- c(class_list, svm_classifier_level(as.data.frame(app_list[as.numeric(i*7+1):as.numeric(i*7+7)]), interval_list[[i+1]][n], interval_list[[i+1]][n+1]))
      #print(paste(n," ",interval_list[[i+1]][n]," - ", interval_list[[i+1]][n+1]))
      
    }
  }
  return(class_list)
}